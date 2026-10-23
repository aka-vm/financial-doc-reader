"""Drop-in web page: give it servicer reports, contracts, loan tapes, a .zip, or an EDGAR link; get one deal report.

usage: python3 app.py --backend ollama --model <model> [--url URL] [--port 8420] [--host 0.0.0.0]   (see STARTUP.md)
The model is chosen when the server starts; the page only takes documents. Uploads live in a temp folder per job.
"""
import argparse
import base64
import json
import os
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reader.deal import build  # noqa: E402
from reader.intake import collect  # noqa: E402

UI = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "reader", "ui.html"), encoding="utf-8").read()
DEFAULTS, JOBS = {}, {}
MAX_UPLOAD = 300 << 20


def work(job, files, links, backend, model, url):
    log = job["log"].append
    job["progress"] = {"done": 0, "total": 0, "step": "collecting the documents"}
    try:
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for f in files:
                p = os.path.join(folder, os.path.basename(f["name"]) or "upload")
                open(p, "wb").write(base64.b64decode(f["data"]))
                paths.append(p)
            docs = collect(paths, links, folder, log)
            if not docs:
                raise ValueError("nothing to read: add a file or a link")
            job["report"] = build(docs, backend, model, url, log,
                                  lambda done, total, step: job.update(progress={"done": done, "total": total, "step": step}))
        job["status"] = "done"
    except Exception as e:  # shown on the page
        job["status"], job["error"] = "error", f"{type(e).__name__}: {e}"


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/jobs/"):
            job = JOBS.get(self.path.rsplit("/", 1)[1])
            return self.send(200, json.dumps(job)) if job else self.send(404, "{}")
        self.send(200, UI, "text/html; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/jobs":
            return self.send(404, "{}")
        size = int(self.headers.get("Content-Length", 0))
        if size > MAX_UPLOAD:
            return self.send(413, json.dumps({"error": "upload larger than 300 MB"}))
        req = json.loads(self.rfile.read(size))
        jid = uuid.uuid4().hex[:12]
        JOBS[jid] = {"status": "running", "log": [], "report": None, "error": None}
        threading.Thread(target=work, daemon=True, args=(
            JOBS[jid], req.get("files", []), [u for u in req.get("links", []) if u.strip()],
            DEFAULTS["backend"], DEFAULTS.get("model"), DEFAULTS.get("url"))).start()
        self.send(200, json.dumps({"id": jid}))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--model")
    ap.add_argument("--url")
    ap.add_argument("--port", type=int, default=8420)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to open the page from other devices on your network")
    a = ap.parse_args()
    DEFAULTS.update(backend=a.backend, model=a.model, url=a.url)
    where = "localhost" if a.host == "127.0.0.1" else "<this machine's address>"
    print(f"open http://{where}:{a.port}  (backend {a.backend}, model {a.model or 'default'})", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
