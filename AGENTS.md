# Setting up servicer-report-reader (instructions for coding agents)

You are helping someone run this project: it reads a monthly auto-loan ABS servicer report (HTML from SEC EDGAR,
text, or PDF) into a fixed set of figures and runs arithmetic checks on them. Every figure either passes the checks or
is flagged with the reason. Follow these steps in order and ask the user only where a step says so.

## 1. Check the basics
- `python3 --version` must be 3.10 or newer. The core needs no packages; `pip install pypdf` only for PDF reports,
  `pip install anthropic` only for the Anthropic API backend.
- Example reports are stored with Git LFS. If `examples/*.htm` are tiny pointer files, run `git lfs install && git lfs pull`.
- Run `python3 -m reader.selftest`. It needs no model and must print `ok: ...`. If it fails, stop and report it.

## 2. Ask the user where the model should run
Ask once, offering these four options (recommend the first two: reports stay on their own hardware):

1. **Local model with Ollama**: install from https://ollama.com, then `ollama pull <model>`. A Qwen model of
   roughly 27B parameters is what this was tested with (needs ~24-48 GB of RAM or GPU memory). Smaller models
   (4-9B) run on a 16 GB laptop but leave more figures flagged.
   Backend: `--backend ollama --model <model>`.
2. **Their own server (a link)**: any OpenAI-compatible endpoint (vLLM, llama.cpp server, LM Studio).
   Ask for the base URL (ends in `/v1`) and the served model name. If the server needs a key, `export LINK_API_KEY=...`.
   Backend: `--backend link --url <URL> --model <name>`.
3. **The coding agent they already use**: `codex`, `claude-code` or `gemini-cli`, using the CLI's existing login.
   Check the CLI is installed (`codex --version`, `claude --version`, `gemini --version`).
   Backend: `--backend codex` (or `claude-code`, `gemini-cli`), `--model` optional.
4. **A hosted model with an API key**: `anthropic`, `openai` or `gemini`. Ask them to set `ANTHROPIC_API_KEY`,
   `OPENAI_API_KEY` or `GEMINI_API_KEY` themselves; never ask them to paste a key into the chat.
   Backend: `--backend anthropic` (default model `claude-opus-5-5`), or `--backend openai|gemini --model <name>`.

Options 3 and 4 send the report to an outside service. Say so before using them.

## 3. Try one example
```
python3 -m reader.extract examples/carmax-2024-1__2026-07-31.htm examples/carmax-2024-1__2026-08-31.htm <backend flags> --out out/
```
Compare `out/*.json` with `examples/*.expected.json` (rule-checked answers). Report how many figures match and how
many were flagged. A flagged figure is the system working, not a failure: it was not trusted.

## 4. Start the page
```
python3 app.py <backend flags>
```
Then tell the user to open http://localhost:8420 and drop a report on it. The backend can also be changed on the page.

## Rules when changing code
- Never edit `reader/checks.py` to make a flag go away on one report. A check must hold for every issuer;
  after any change, `python3 -m reader.selftest` must still pass (it fails if a check fires on a correct answer).
- Keep the model's job to reading, not arithmetic: totals and precision are fixed in code (`checks.finalize`, `checks.exact`).
- Keep temperature 0 and the JSON schema on every backend.
