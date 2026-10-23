"""Where the model runs. Every backend takes the same prompt and JSON schema and returns the parsed JSON.

  ollama      a model on this machine (default http://localhost:11434, or OLLAMA_HOST)
  link        any OpenAI-compatible server you host: vLLM, llama.cpp, LM Studio (--url, optional LINK_API_KEY)
  codex | claude-code | gemini-cli
              the coding agent you already have installed and logged in; it runs the prompt, no tools
  anthropic | openai | gemini
              a hosted model with your API key (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY)
"""
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request

AGENTS = {"codex", "claude-code", "gemini-cli"}
HOSTED_URLS = {"openai": "https://api.openai.com/v1", "gemini": "https://generativelanguage.googleapis.com/v1beta/openai"}
DEFAULT_MODEL_ANTHROPIC = "claude-opus-5-5"  # openai / gemini: pass --model


def first_json(text):
    """The first complete JSON object in a reply (agents may wrap it in a code fence or add a sentence)."""
    return json.JSONDecoder().raw_decode(text[text.index("{"):])[0]


RUNAWAY = 300  # this many whitespace characters in a row: valid JSON never needs it; the model is looping


def post(url, body, headers=None, timeout=1800):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


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


def ollama(model, prompt, schema, max_tokens=16384):
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    host = host if host.startswith("http") else "http://" + host
    body = {"model": model, "stream": True, "format": schema, "think": False, "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_ctx": 32768, "num_predict": max_tokens}}
    try:
        text = stream(f"{host}/api/chat", body, lambda ln: ln and json.loads(ln).get("message", {}).get("content"))
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


def call(backend, model, prompt, schema, url=None, max_tokens=16384):
    """One answer as parsed JSON. Constrained JSON can loop on whitespace until the length limit (max_tokens is only
    that safety net, set far above any real answer); a broken answer is asked for again with a different prompt,
    since at temperature 0 the same prompt would loop the same way."""
    try:
        return _call(backend, model, prompt, schema, url, max_tokens)
    except (ValueError, KeyError):  # json.JSONDecodeError is a ValueError
        pass
    try:
        return _call(backend, model, prompt + RETRY, schema, url, max_tokens)
    except (ValueError, KeyError) as e:
        raise RuntimeError(f"the model's answer was not valid JSON, also on a retry ({e})") from e


def _call(backend, model, prompt, schema, url, max_tokens):
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
    if backend in HOSTED_URLS:
        return openai_compatible(HOSTED_URLS[backend], model, prompt, schema, os.environ[f"{backend.upper()}_API_KEY"], max_tokens)
    raise ValueError(f"unknown backend {backend!r}")
