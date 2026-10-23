# Starting the server

The model is chosen once, when the server starts. People using the page only drop documents; they never pick a
model. Pick one of the four ways below, start `app.py` with its flags, and share `http://localhost:8420`.

## 0. Before the first start
- Python 3.10 or newer. No packages are required; `pip install pypdf` for PDF reports, `pip install anthropic` for
  the Anthropic backend.
- Example documents are in Git LFS: `git lfs install && git lfs pull`.
- `python3 -m reader.selftest` must print `ok: ...` (no model needed).
- EDGAR links: SEC asks for a contact in every request, so set `export SEC_USER_AGENT="Your Name you@example.com"`.

## 1. Pick where the model runs

**1. A local model with Ollama** (documents stay on this machine)
```
ollama pull <model>
python3 app.py --backend ollama --model <model>
```
Tested with a 27B Qwen model (needs about 24-48 GB of RAM or GPU memory). Smaller models (4-9B) run on a 16 GB
laptop but leave more figures flagged. Set `OLLAMA_HOST` if Ollama runs elsewhere.

**2. Your own GPU server, by link** (vLLM, llama.cpp server, LM Studio: any OpenAI-compatible endpoint)
```
curl http://my-gpu-box:8000/v1/models          # check it answers and note the model name
python3 app.py --backend link --url http://my-gpu-box:8000/v1 --model <served model name>
```
If the server needs a key: `export LINK_API_KEY=...`. If it only listens on its own localhost, tunnel to it first
(`ssh -N -L 8001:localhost:8000 user@my-gpu-box`) and use `--url http://localhost:8001/v1`.

**3. A coding agent you are already signed in to** (`codex`, `claude-code` or `gemini-cli`)
```
python3 app.py --backend codex            # or claude-code / gemini-cli; --model is optional
```

**4. A hosted model with an API key** (`anthropic`, `openai` or `gemini`)
```
export ANTHROPIC_API_KEY=...              # or OPENAI_API_KEY / GEMINI_API_KEY
python3 app.py --backend anthropic        # default model claude-opus-5-5; openai / gemini need --model
```

Ways 3 and 4 send documents to an outside service; 1 and 2 keep them on your hardware.

## 2. Open it
- `http://localhost:8420` on this machine. Change the port with `--port`.
- To let other devices on a private network (e.g. Tailscale) use it, add `--host 0.0.0.0` and share
  `http://<this machine's network address>:8420`. There is no login: anyone who can reach that address can use it.

To change the model, stop the server and start it again with other flags.
