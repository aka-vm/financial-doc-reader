"""Single-process web host. Disk-backed expiring reports; bounded concurrent background jobs."""
import json
from concurrent.futures import ThreadPoolExecutor
import os
import secrets
import shutil
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from . import engine, bundles
from reader.backends import ModelError, openai_key, LLM_ROUTER
from .llm_config import load_registry


def create_app(config=None):
    # Private model traffic needs no system proxy discovery. On macOS that discovery
    # can initialize Objective-C after Gunicorn forks and crash a threaded worker.
    if os.environ.get("BRIEF_USE_ENV_PROXY") != "1":
        urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    # Non-secret local settings persist across development and Gunicorn restarts.
    settings_path = Path(os.environ.get("BRIEF_CONFIG", ".brief-config.json")).expanduser()
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(SECRET_KEY=os.environ.get("BRIEF_SECRET"),
                      MAX_CONTENT_LENGTH=300 << 20, MAX_FORM_MEMORY_SIZE=512 << 10,
                      MAX_FORM_PARTS=110, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Strict",
                      SESSION_COOKIE_NAME="ledger_session",
                      SESSION_COOKIE_SECURE=os.environ.get("BRIEF_HTTPS") == "1",
                      DATA_DIR=os.environ.get("BRIEF_DATA", ".brief-data"),
                      BACKEND=os.environ.get("BRIEF_BACKEND", settings.get("backend", "link")),
                      MODEL=os.environ.get("BRIEF_MODEL", settings.get("model",
                          "gpt-5-mini" if os.environ.get("BRIEF_BACKEND", settings.get("backend")) == "openai" else "qwen3.8")),
                      MODEL_URL=os.environ.get("BRIEF_MODEL_URL", settings.get("url", "http://127.0.0.1:8001/v1")),
                      TTL=3600, MAX_JOBS=int(os.environ.get("BRIEF_MAX_JOBS", "40")), CONCURRENCY=int(os.environ.get("BRIEF_CONCURRENCY", "2")))
    if config:
        app.config.update(config)
    model_settings = {
        "extract": os.environ.get("BRIEF_EXTRACT_MODEL", settings.get("extract_model", app.config["MODEL"])),
        "write": os.environ.get("BRIEF_WRITE_MODEL", settings.get("write_model", app.config["MODEL"])),
        "review": os.environ.get("BRIEF_REVIEW_MODEL", settings.get("review_model", app.config["MODEL"]))}
    if config:
        model_settings.update(config.get("MODELS", {}))
    app.config["MODELS"] = model_settings
    registry_path=os.environ.get("BRIEF_LLM_CONFIG", settings.get("llm_config"))
    if not registry_path and Path("llm-config.json").exists():registry_path="llm-config.json"
    if config and config.get("TESTING") and "LLM_CONFIG" not in config:registry_path=None
    if config and "LLM_CONFIG" in config:registry_path=config["LLM_CONFIG"]
    app.config["LLM_CONFIG"]=registry_path
    if registry_path:load_registry(registry_path)

    def registry_snapshot():
        return load_registry(app.config["LLM_CONFIG"]) if app.config["LLM_CONFIG"] else None

    if app.config["BACKEND"] not in {"link", "openai"}:
        raise ValueError("BRIEF_BACKEND must be link or openai.")
    if app.config["BACKEND"] == "openai" and not registry_path:
        openai_key()  # Fail at startup when credentials are missing, before accepting uploads.
    # Enable only behind a single trusted reverse proxy that overwrites X-Forwarded-Proto.
    if os.environ.get("BRIEF_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0)
    root = Path(app.config["DATA_DIR"]).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not app.config["SECRET_KEY"]:
        # Reuse the same signing key across restarts, without putting it in Git.
        secret_file = root / ".session-secret"
        try:
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as stream:
                stream.write(secrets.token_hex(32))
        app.config["SECRET_KEY"] = secret_file.read_text().strip()
        if len(app.config["SECRET_KEY"]) < 32:
            raise ValueError("Invalid session signing key in the data directory.")
    if not 1 <= app.config["CONCURRENCY"] <= 4:
        raise ValueError("BRIEF_CONCURRENCY must be between 1 and 4.")
    gate, lock = threading.BoundedSemaphore(app.config["CONCURRENCY"]), threading.RLock()
    slots = threading.BoundedSemaphore(6)
    executor = ThreadPoolExecutor(max_workers=app.config["CONCURRENCY"], thread_name_prefix="ledger-reader")
    rates = {}

    # One process owns this directory. Recover interrupted jobs and remove their uploads.
    for path in root.glob("upload-*"):
        if path.is_dir():
            shutil.rmtree(path)
    for path in root.glob("*.json"):
        try:
            state = json.loads(path.read_text())
            if time.time() - state["created"] > app.config["TTL"]:
                path.unlink()
            elif state["status"] in {"queued", "running"}:
                state.update(status="error", error="The reader restarted before finishing. Please upload again.")
                path.write_text(json.dumps(state))
            elif state.get("answer_job", {}).get("status") == "running":
                state["answer_job"].update(status="error", error="The reader restarted. Please ask again.")
                path.write_text(json.dumps(state))
        except (OSError, ValueError, KeyError):
            app.logger.warning("Could not recover an old report snapshot")

    def save(jid, state):
        # Every reader sees either the old or the complete new snapshot.
        with lock:
            target = root / f"{jid}.json"
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            tmp.replace(target)

    def load(jid):
        if len(jid) != 32 or any(c not in "0123456789abcdef" for c in jid):
            return None
        path = root / f"{jid}.json"
        try:
            job = json.loads(path.read_text())
            if job["owner"] != session.get("owner") or time.time() - job["created"] > app.config["TTL"]:
                return None
            return job
        except (OSError, ValueError):
            return None

    def cleanup_loop():
        while True:
            time.sleep(60)
            with lock:
                for path in root.glob("*.json"):
                    if time.time() - path.stat().st_mtime > app.config["TTL"]:
                        path.unlink(missing_ok=True)

    if not app.config.get("TESTING"):
        threading.Thread(target=cleanup_loop, daemon=True).start()

    @app.before_request
    def boundary():
        if request.method in {"POST", "DELETE"}:
            # Cross-origin forms cannot set this header. No CORS permission is granted.
            if request.headers.get("X-Brief-Request") != "1":
                return jsonify(error="Reload the page before submitting."), 403
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="Cross-origin requests are not allowed."), 403
            if not session.get("owner"):
                return jsonify(error="Open the home page before submitting."), 403
            now = time.time()
            with lock:
                for key in list(rates):
                    rates[key] = [t for t in rates[key] if now - t < 3600]
                    if not rates[key]:
                        del rates[key]
                peer = request.remote_addr
                starts = rates.setdefault(peer, [])
                if len(starts) >= 30 or len(rates) > 1000:
                    return jsonify(error="Request limit reached. Please try again later."), 429
                starts.append(now)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.errorhandler(Exception)
    def error(exc):
        if isinstance(exc, HTTPException):
            return jsonify(error="Upload exceeds the 300 MB limit." if exc.code == 413 else exc.description), exc.code
        app.logger.exception("Request failed")
        return jsonify(error="The request could not be completed. Please retry."), 500

    @app.get("/")
    def home():
        if not session.get("owner"):
            session["owner"] = secrets.token_hex(24)
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/healthz")
    def health():
        registry=registry_snapshot()
        if registry:
            return jsonify(status="ok", backend="registry", model=registry.models()["extract"],
                           models=registry.models(), llm_tasks=registry.describe(),
                           config_revision=registry.revision, concurrency=app.config["CONCURRENCY"])
        return jsonify(status="ok", backend=app.config["BACKEND"], model=app.config["MODEL"], models=app.config["MODELS"], concurrency=app.config["CONCURRENCY"])

    @app.get("/api/examples")
    def examples_catalog():
        return jsonify(json.loads((Path(__file__).parent / "examples" / "catalog.json").read_text()))

    @app.get("/examples/<name>")
    def example_document(name):
        directory = Path(__file__).parent / "examples"
        catalog = json.loads((directory / "catalog.json").read_text())
        item = next((item for item in catalog if item["name"] == name), None)
        if item is None:
            return jsonify(error="Example not found."), 404
        return send_from_directory(directory, item.get("asset", name))

    @app.get("/example.txt")
    def example():
        return send_from_directory(Path(__file__).parent / "examples", "northstar-2025.txt", mimetype="text/plain")

    def run(jid, state, folder, paths, mode="brief"):
        gate.acquire()
        router_token=None
        try:
            registry=registry_snapshot()
            job_backend="registry" if registry else app.config["BACKEND"]
            job_models={task:"task:"+task for task in registry.routes} if registry else app.config["MODELS"]
            if registry:
                router_token=LLM_ROUTER.set(registry)
                state["llm_tasks"],state["config_revision"]=registry.describe(),registry.revision
            state["status"] = "running"
            save(jid, state)
            def progress(done, total, label):
                state["progress"] = {"done": done, "total": total, "label": label}
                save(jid, state)
            paths, warnings = bundles.prepare(paths, folder)
            if mode == "deal":
                report = bundles.build_deal(paths, folder, job_backend, job_models.get("contract",job_models["write"]), app.config["MODEL_URL"], progress, job_models["extract"], job_models.get("month_inputs",job_models["extract"]))
                report["deal"]["notes"].extend(warnings)
                from reader.deal import to_markdown
                report["markdown"] = to_markdown(report["deal"])
            else:
                if len(paths) > 5 or sum(p.stat().st_size for p in paths) > 16 << 20:
                    raise ValueError("Financial briefs accept up to 5 documents and 16 MB. Choose ABS deal report for a larger deal bundle.")
                report = engine.build(paths, app.config["MODEL"], app.config["MODEL_URL"], progress, backend=job_backend, models=job_models)
                report.setdefault("warnings", []).extend(warnings)
            if registry:
                report["models"],report["llm_tasks"],report["config_revision"]=registry.models(),registry.describe(),registry.revision
            state.update(status="done", report=report)
        except (ValueError, ModelError) as exc:
            state.update(status="error", error=str(exc))
        except Exception:
            app.logger.exception("Brief generation failed")
            state.update(status="error", error="Could not finish reading. The model may be unavailable or the file unreadable. Please retry.")
        finally:
            if router_token is not None:LLM_ROUTER.reset(router_token)
            shutil.rmtree(folder, ignore_errors=True)
            try:
                save(jid, state)
            finally:
                gate.release()
                slots.release()

    @app.post("/api/briefs")
    def submit():
        if not slots.acquire(blocking=False):
            return jsonify(error="The reader queue is full (6 reports). Please try again shortly."), 429
        folder = None
        handed_off = False
        try:
            # Bound disk retention and metadata even under repeated public submissions.
            if len(list(root.glob("*.json"))) >= app.config["MAX_JOBS"]:
                return jsonify(error="The reader has reached its hourly capacity. Please try again later."), 429
            files = request.files.getlist("files")
            mode = request.form.get("mode", "brief")
            if mode not in {"brief", "deal"}:
                return jsonify(error="Choose Financial brief or ABS deal report."), 400
            if mode == "brief" and request.content_length and request.content_length > 16 << 20:
                return jsonify(error="Financial briefs have a 16 MB limit. Choose ABS deal report for a larger bundle."), 413
            if not 1 <= len(files) <= (100 if mode == "deal" else 5):
                return jsonify(error="Choose between 1 and 100 files for a deal, or up to 5 for a brief."), 400
            folder = tempfile.mkdtemp(prefix="upload-", dir=root)
            paths, names = [], set()
            for upload in files:
                name = bundles.relative_name(upload.filename or "")
                if name is None:
                    return jsonify(error="Supported files: PDF, TXT, HTML, CSV, XML, and ZIP."), 400
                if name in names:
                    return jsonify(error="Each file in a bundle must have a different name."), 400
                names.add(name)
                path = Path(folder) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                upload.save(path)
                paths.append(path)
            jid = secrets.token_hex(16)
            state = {"owner": session["owner"], "created": time.time(), "status": "queued",
                     "progress": {"done": 0, "total": 1, "label": "Queued — waiting for the reader"},
                     "report": None, "error": None}
            save(jid, state)
            executor.submit(run, jid, state, folder, paths, mode)
            handed_off = True
            return jsonify(id=jid), 202
        finally:
            if not handed_off:
                if folder:
                    shutil.rmtree(folder, ignore_errors=True)
                slots.release()

    @app.get("/api/briefs/<jid>")
    def get_brief(jid):
        job = load(jid)
        if job is None:
            return jsonify(error="Brief not found or expired."), 404
        public = {k: v for k, v in job.items() if k != "owner"}
        if public.get("report"):
            public["report"] = {k: v for k, v in public["report"].items() if not k.startswith("_")}
            if public["report"].get("type") != "deal" and "subjects" not in public["report"]:
                from .identity import identify
                public["report"]["subjects"] = identify(job["report"].get("_sources", []))
            if public["report"].get("type") != "deal" and "visuals" not in public["report"]:
                from .visuals import build_views
                public["report"]["visuals"] = build_views(public["report"].get("facts", []))
        return jsonify(public)

    @app.post("/api/briefs/<jid>/ask")
    def ask(jid):
        job = load(jid)
        if not job or job["status"] != "done":
            return jsonify(error="Brief not found or not ready."), 404
        if job.get("answer_job", {}).get("status") == "running":
            return jsonify(error="A question for this brief is already being answered."), 429
        if job["report"].get("type") == "deal":
            return jsonify(error="Follow-up questions are available for financial briefs. See Needs review in the deal report."), 400
        body = request.get_json(silent=True) or {}
        question = body.get("question", "")
        if not isinstance(question, str) or not 3 <= len(question.strip()) <= 500:
            return jsonify(error="Ask a question between 3 and 500 characters."), 400
        if not gate.acquire(blocking=False):
            return jsonify(error="The reader is busy. Please try again shortly."), 429
        aid = secrets.token_hex(16)
        job["answer_job"] = {"id": aid, "status": "running"}
        try:
            save(jid, job)
            threading.Thread(target=run_answer, args=(jid, job, question), daemon=True).start()
        except Exception:
            gate.release()
            raise
        return jsonify(id=aid, status="running"), 202

    def run_answer(jid, job, question):
        router_token=None
        try:
            registry=registry_snapshot()
            if registry:router_token=LLM_ROUTER.set(registry)
            result = engine.answer(question, job["report"], "task:answer" if registry else app.config["MODELS"]["write"], app.config["MODEL_URL"], backend="registry" if registry else app.config["BACKEND"])
            if registry:job["answer_job"]["llm_task"]=registry.describe()["answer"]
            job["answer_job"].update(status="done", result=result)
        except (ModelError,ValueError) as exc:
            job["answer_job"].update(status="error", error=str(exc))
        except Exception:
            app.logger.exception("Follow-up question failed")
            job["answer_job"].update(status="error", error="Could not answer. The model may be unavailable. Please retry.")
        finally:
            if router_token is not None:LLM_ROUTER.reset(router_token)
            try:
                save(jid, job)
            finally:
                gate.release()

    @app.get("/api/briefs/<jid>/answers/<aid>")
    def get_answer(jid, aid):
        job = load(jid)
        answer_job = (job or {}).get("answer_job", {})
        if answer_job.get("id") != aid:
            return jsonify(error="Answer not found or expired."), 404
        return jsonify(answer_job)

    @app.delete("/api/briefs/<jid>")
    def delete(jid):
        job = load(jid)
        if not job:
            return jsonify(error="Brief not found."), 404
        if job["status"] in {"queued", "running"} or job.get("answer_job", {}).get("status") == "running":
            return jsonify(error="Wait until reading finishes before deleting."), 409
        with lock:
            (root / f"{jid}.json").unlink(missing_ok=True)
        return jsonify(deleted=True)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 8422)), threaded=True)
