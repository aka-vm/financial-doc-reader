"""Where the model runs. Every backend takes the same prompt and JSON schema and returns the parsed JSON.

  ollama      a model on this machine (default http://localhost:11434, or OLLAMA_HOST)
  link        any OpenAI-compatible server you host: vLLM, llama.cpp, LM Studio (--url, optional LINK_API_KEY)
  codex | claude-code | gemini-cli
              the coding agent you already have installed and logged in; it runs the prompt, no tools
  anthropic | openai | gemini
              a hosted model with your API key (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)
"""
import json
from contextvars import ContextVar
import os
from pathlib import Path
import subprocess
import ssl
import tempfile
import urllib.error
import urllib.request

LLM_ROUTER = ContextVar("llm_router", default=None)

AGENTS = {"codex", "claude-code", "gemini-cli"}
HOSTED_URLS = {"openai": "https://api.openai.com/v1", "gemini": "https://generativelanguage.googleapis.com/v1beta/openai"}
DEFAULT_MODEL_ANTHROPIC = "claude-opus-5-5"  # openai / gemini: pass --model


def first_json(text):
    """The first complete JSON object in a reply (agents may wrap it in a code fence or add a sentence)."""
    return json.JSONDecoder().raw_decode(text[text.index("{"):])[0]


RUNAWAY = 300  # this many whitespace characters in a row: valid JSON never needs it; the model is looping


def post(url, body, headers=None, timeout=1800, context=None):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    if context is not None:
        # urlopen(context=...) builds a fresh opener, which otherwise discovers
        # macOS system proxies even when the server installed a proxy-free opener.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(urllib.request.getproxies_environment()),
            urllib.request.HTTPSHandler(context=context))
        with opener.open(req, timeout=timeout) as response:
            return json.load(response)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def stream(url, body, piece, headers=None, timeout=1800):
    """Read a streamed answer chunk by chunk (piece(line) -> text or None); stop as soon as it starts looping on
    whitespace, instead of letting it run to the length limit."""
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return gather(piece(line.decode("utf-8", "replace").strip()) for line in r)


def gather(chunks):
    """Join streamed text chunks; raise as soon as RUNAWAY whitespace characters arrive in a row."""
    text, blank = [], 0
    for t in chunks:
        if not t:
            continue
        text.append(t)
        blank = blank + len(t) if not t.strip() else len(t) - len(t.rstrip())
        if blank >= RUNAWAY:
            raise ValueError("the answer started repeating whitespace")
    return "".join(text)


def ollama(model, prompt, schema, max_tokens=16384, host=None, key=None):
    host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    host = (host if host.startswith("http") else "http://" + host).rstrip("/")
    body = {"model": model, "stream": True, "format": schema, "think": False, "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_ctx": 32768, "num_predict": max_tokens}}
    try:
        text = stream(f"{host}/api/chat", body, lambda ln: ln and json.loads(ln).get("message", {}).get("content"), headers={"Authorization": f"Bearer {key}"} if key else {})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f"Ollama has no model {model!r}: run `ollama pull {model}`") from e
        raise
    return json.loads(text)


def _sse(line):
    if not line.startswith("data:") or line.endswith("[DONE]"):
        return None
    choices = json.loads(line[5:]).get("choices") or [{}]
    return (choices[0].get("delta") or {}).get("content")


def openai_compatible(url, model, prompt, schema, key=None, max_tokens=16384, **extra):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "stream": True,
            "response_format": {"type": "json_schema", "json_schema": {"name": "report", "schema": schema}}, **extra}
    text = stream(url.rstrip("/") + "/chat/completions", body, _sse, {"Authorization": f"Bearer {key}"} if key else {})
    return first_json(text)


class ModelError(RuntimeError):
    """A safe, actionable provider error that may be displayed to the user."""


def openai_key(env="OPENAI_API_KEY", key_file=None):
    key = os.environ.get(env, "").strip()
    if not key:
        path = Path(key_file or os.environ.get("OPENAI_API_KEY_FILE", "~/.openai_key")).expanduser()
        try:
            key = path.read_text().strip()
        except OSError:
            raise ModelError("OpenAI key unavailable. Set OPENAI_API_KEY or OPENAI_API_KEY_FILE on the server.") from None
        if key.startswith("export "):
            key = key[7:].strip()
        if key.startswith("OPENAI_API_KEY="):
            key = key.split("=", 1)[1].strip()
        key = key.strip("\"'")
    if not key or any(c.isspace() for c in key):
        raise ModelError("Invalid OpenAI key file. Use a single API key or set OPENAI_API_KEY on the server.")
    return key


def closed_schema(schema):
    """Strict OpenAI output requires closed objects; waterfall specs contain open maps."""
    if isinstance(schema, dict):
        if schema.get("type") == "object" and (schema.get("additionalProperties") is not False or
                set(schema.get("required", [])) != set(schema.get("properties", {}))):
            return False
        return all(closed_schema(value) for value in schema.values())
    if isinstance(schema, list):
        return all(closed_schema(value) for value in schema)
    return True


def openai(model, prompt, schema, max_tokens=16384, reasoning_effort=None, key=None):
    # Reasoning models use their supported effort setting and default sampling.
    body = {"model": model, "input": prompt, "store": False,
            "max_output_tokens": max_tokens,
            "text": {"format": {"type": "json_schema", "name": "report", "strict": closed_schema(schema), "schema": schema}}}
    if model.startswith(("gpt-5-mini", "gpt-5-nano")):
        body["reasoning"] = {"effort": reasoning_effort or "minimal"}
    elif model.startswith(("gpt-5.6-luna", "gpt-6-luna")):
        body["reasoning"] = {"effort": reasoning_effort or "low"}
    else:
        body["temperature"] = 0
    import certifi
    # Avoid macOS Keychain discovery after Gunicorn forks: it can abort the worker.
    # TLS client defaults still require a valid certificate and matching hostname.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(certifi.where())
    try:
        result = post("https://api.openai.com/v1/responses", body,
                      {"Authorization": f"Bearer {openai_key() if key is None else key}"}, timeout=180, context=context)
    except urllib.error.HTTPError as exc:
        messages = {
            400: "OpenAI rejected the model request or output schema. Check the server configuration.",
            401: "OpenAI rejected the API key. Update the key on the server.",
            403: "The OpenAI project does not have permission to use this model.",
            404: f"OpenAI model {model!r} is unavailable to this project. Check BRIEF_MODEL.",
            429: "OpenAI rate limit or quota reached. Check API billing and retry shortly.",
        }
        raise ModelError(messages.get(exc.code, f"OpenAI is unavailable (HTTP {exc.code}). Please retry.")) from None
    except (urllib.error.URLError, TimeoutError):
        raise ModelError("Cannot reach OpenAI. Check the server's internet connection and DNS, then retry.") from None
    if result.get("status") != "completed":
        raise ModelError("OpenAI did not finish the response. Try a smaller document or retry.")
    parts = [part for item in result.get("output", []) if item.get("type") == "message"
             for part in item.get("content", [])]
    if any(part.get("type") == "refusal" for part in parts):
        raise ModelError("OpenAI declined to process this content.")
    text = "".join(part.get("text", "") for part in parts if part.get("type") == "output_text")
    if not text:
        raise ModelError("OpenAI returned no report text. Please retry.")
    return json.loads(text)


def anthropic(model, prompt, schema):
    import anthropic as sdk  # pip install anthropic
    client = sdk.Anthropic()  # ANTHROPIC_API_KEY
    res = client.beta.messages.create(
        model=model, max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",  # a declined request is retried on another model
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if res.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {res.stop_details}")
    return json.loads(next(b.text for b in res.content if b.type == "text"))


def agent(name, model, prompt):
    """Run the prompt through a coding-agent CLI the user is already signed in to (no tools needed)."""
    if name == "codex":
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "answer.txt")
            cmd = ["codex", "exec", "-s", "read-only", "--skip-git-repo-check", "-o", out, "-"]
            subprocess.run(cmd[:2] + (["-m", model] if model else []) + cmd[2:], input=prompt, text=True,
                           capture_output=True, timeout=1800, cwd=d, check=True)
            return first_json(open(out).read())
    cmd = (["claude", "-p", "--output-format", "text"] if name == "claude-code"
           else ["gemini", "-p", "Answer the request above.", "--approval-mode", "plan", "-o", "text"])
    if model:
        cmd += ["--model", model]
    r = subprocess.run(cmd, input=prompt, text=True, capture_output=True, timeout=1800, check=True)
    return first_json(r.stdout)


RETRY = ("\n\nYour previous answer broke off before the JSON was complete (it repeated spaces or newlines). "
         "Write the JSON compactly on a single line, with no spaces between items.")


def call(backend, model, prompt, schema, url=None, max_tokens=16384, reasoning_effort=None):
    """One answer as parsed JSON. Constrained JSON can loop on whitespace until the length limit (max_tokens is only
    that safety net, set far above any real answer); a broken answer is asked for again with a different prompt,
    since at temperature 0 the same prompt would loop the same way."""
    try:
        return _call(backend, model, prompt, schema, url, max_tokens, reasoning_effort)
    except (ValueError, KeyError):  # json.JSONDecodeError is a ValueError
        pass
    try:
        return _call(backend, model, prompt + RETRY, schema, url, max_tokens, reasoning_effort)
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"the model's answer was not valid JSON, also on a retry ({e})") from e


def _call(backend, model, prompt, schema, url, max_tokens, reasoning_effort=None):
    if backend == "registry":
        router=LLM_ROUTER.get()
        if router is None:raise ModelError("No LLM registry snapshot was assigned to this job.")
        return router.invoke(model,prompt,schema,max_tokens,reasoning_effort)
    if backend == "ollama":
        return ollama(model, prompt, schema, max_tokens)
    if backend == "link":
        key = os.environ.get("LINK_API_KEY")
        try:  # temperature 0; Qwen-style templates on vLLM answer directly instead of thinking first
            return openai_compatible(url, model, prompt, schema, key, max_tokens, temperature=0,
                                     chat_template_kwargs={"enable_thinking": False})
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            return openai_compatible(url, model, prompt, schema, key, max_tokens, temperature=0)  # proxy rejects the field
    if backend in AGENTS:
        return agent(backend, model, prompt)
    if backend == "anthropic":
        return anthropic(model or DEFAULT_MODEL_ANTHROPIC, prompt, schema)
    if backend == "openai":
        return openai(model, prompt, schema, max_tokens, reasoning_effort)
    if backend in HOSTED_URLS:
        return openai_compatible(HOSTED_URLS[backend], model, prompt, schema, os.environ[f"{backend.upper()}_API_KEY"], max_tokens)
    raise ValueError(f"unknown backend {backend!r}")
