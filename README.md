# Ledger / Deal Report Reader

Read financial documents, follow every figure back to its source, and turn a complete
auto-loan ABS deal into checked monthly figures, payment rules and loan-pool statistics.
Built by [Vineet](https://aka-vm.github.io) · [GitHub](https://github.com/aka-vm/servicer-report-reader).

The browser app has two modes:

- **Financial brief:** PDF, HTML, TXT and CSV documents become an overview, material
  figures, highlights, risks, source quotations and follow-up answers. Tables are
  available for reported figures; comparison charts appear only when compatible
  metrics, periods and units are supported by the extracted evidence.
- **ABS deal report:** upload a folder or ZIP of contracts, monthly servicer reports
  and SEC ABS-EE CSV/XML tapes. Code checks arithmetic, balance carryovers, payment
  waterfalls and tape reconciliation. Anything unconfirmed is listed under Needs review.

The library contains 50 substantial public examples, including Eternal/Zomato,
Zerodha, Reliance, HDFC Bank, TCS, Wipro, global issuer releases, SEC monthly filings
and full loan deals. The page displays only six random examples at a time, with a
shuffle control. Each links to its original source and discloses its period/scope.
Loading an example does not run a model until you submit it.

## Start here

**Using a coding agent?** Give it [AGENTS.md](AGENTS.md), or [agent.MD](agent.MD).
It must first establish your provider/model choices and credential references,
reusing choices you have already supplied. It must not assume you want a paid API.

For manual setup, follow [SETUP.md](SETUP.md). From the repository root:

```sh
python3 -m venv .venv-brief
.venv-brief/bin/pip install -r requirements-brief.txt
# Original example files use Git LFS. Install git-lfs if it is not available.
git lfs install
git lfs pull
python3 -m reader.selftest
.venv-brief/bin/python -m unittest discover -s tests -v
```

Choose your LLMs before starting the app. The template uses GPT-5 nano for simple
extraction and GPT-6 Luna for difficult tables, writing and checking:

```sh
cp llm-config.example.json llm-config.json
# Edit the file for your providers, endpoints, model IDs and credential references.
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json
# Optional: one small provider request per selected LLM; hosted requests may be billed.
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json --test
.venv-brief/bin/python -m financial_brief.server
```

Open **http://localhost:8422**. Put API keys in server environment variables or private
key files, never in the JSON registry or browser. Two reports run concurrently by
default; additional uploads queue. Export JSON, Markdown, figures CSV, or print to PDF.

## Choose an LLM for each task

[llm-config.example.json](llm-config.example.json) separates the registry from task routing:

```json
{
  "version": 1,
  "llms": {
    "nano": {"provider": "openai", "model": "gpt-5-nano", "api_key_env": "OPENAI_API_KEY"},
    "luna": {"provider": "openai", "model": "gpt-6-luna", "api_key_env": "OPENAI_API_KEY"},
    "local": {"provider": "link", "model": "your-served-model-id", "base_url": "http://127.0.0.1:8000/v1"}
  },
  "tasks": {
    "extract": "nano",
    "extract_tables": "luna",
    "recover_extract": "luna",
    "write": "luna",
    "review": "luna",
    "answer": "luna",
    "contract": "luna",
    "month_inputs": "nano"
  }
}
```

To use your own server for everything, point every task at `local`. `link` supports
OpenAI-compatible endpoints such as vLLM, LM Studio or a hosted gateway. `ollama`
supports Ollama's native API. Tasks may use different endpoints and credentials.
Task objects can also set reasoning effort and output-token budgets. See
[LLM routing](docs/agent/LLM_ROUTING.md) for validation, credential precedence and examples.

Configuration is read when a job starts, then held stable for that job. Changes apply
to subsequent jobs without a server restart. Reports record the selected models and
configuration revision. `/healthz` exposes safe routing metadata, not keys or endpoints.

## What the checks establish

Quoted values must occur in extracted source text. Header context supplies explicit
periods, units and scope; a second model pass checks material claims and displayed
figures. These checks do not establish accounting accuracy or audit the source.
Generic briefs do not run the ABS reconciliation engine.

Scanned/image-only content needs OCR and is reported as a coverage limitation. PDFs
that permit reading with an empty password are supported; password-protected PDFs
still require an unlocked copy. Figures are never invented to fill unreadable charts.

Private documents go to the providers selected in your registry. Fully local routing
keeps model requests on those configured endpoints. Uploaded originals are removed
after processing; session-owned reports expire after one hour by default.

## Hosting, evaluation and development

- [Setup and deployment](SETUP.md)
- [Architecture](docs/agent/ARCHITECTURE.md)
- [Model configuration](docs/agent/LLM_ROUTING.md)
- [Operations and troubleshooting](docs/agent/OPERATIONS.md)
- [Evaluation approach and limits](docs/agent/EVALUATION.md)
- [Development handoff](docs/agent/HANDOFF.md)
- [Original ABS CLI, MCP and historical Qwen results](docs/ABS_READER.md), [STARTUP.md](STARTUP.md)

Independent example evaluation uses **agy**, with Gemini Flash coordinating reviews.
It is optional development tooling, not a dependency for running the app. Exact
model versions, fallback reviewers and findings are retained in evaluation artifacts;
a favorable score is not an audit opinion.

Example cards carry up to three tags (report type, topic and region). The six-card
selection samples report types equally before repeating a type, so the larger SEC
servicer collection does not dominate. The library includes full annual reports,
earnings releases, management updates, earnings calls, proxy statements, servicer
reports and complete ABS bundles. Add examples through `financial_brief/examples/catalog.json`
with `report_type` and `tags`; no extra service or model call is required.
