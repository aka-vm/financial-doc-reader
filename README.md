# Financial Doc Reader

Read financial documents and follow every figure back to the sentence or table it came
from. For auto-loan ABS deals, go further: check each monthly servicer report's
arithmetic, run the contract's payment waterfall against what was actually paid, and
reconcile the loan tape to the pool balance.

Built by [Vineet](https://aka-vm.github.io). The browser app is called **Ledger**.

## What it does

**Financial brief.** Drop in PDF, HTML, TXT or CSV documents (annual reports, earnings
releases, earnings calls, proxy statements, management updates). You get an overview,
material figures, highlights and risks, each with its source quotation, and can ask
follow-up questions. Charts appear only when the extracted figures share compatible
metrics, periods and units.

**ABS deal report.** Drop in a folder or ZIP of contracts, monthly servicer reports
and SEC ABS-EE loan tapes, or paste an EDGAR link. Code, not the model, checks totals,
balance carryovers, the payment waterfall and tape reconciliation. Anything it cannot
confirm is listed under *Needs review*.

The page has 53 public examples, six shown at a time: Eternal/Zomato, Zerodha,
Reliance, HDFC Bank, Bajaj Finance, TCS, Wipro, SoFi, Apple, NVIDIA, Berkshire, the
Federal Reserve's bank lending survey, SEC servicer filings and complete loan deals.
Each links to its original source. Loading an example runs no model until you submit it.

## Quick start

Using a coding agent (Claude Code, Codex)? Point it at [AGENTS.md](AGENTS.md). It will
ask which models you want before calling any of them.

Otherwise, from the repository root (Python 3.10+):

```sh
python3 -m venv .venv-brief
.venv-brief/bin/pip install -r requirements-brief.txt
git lfs install && git lfs pull          # the original ABS example reports use Git LFS
python3 -m reader.selftest               # no model needed; must print "ok: ..."

cp llm-config.example.json llm-config.json
# edit llm-config.json: providers, model IDs, endpoints, credential references
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json          # validate
.venv-brief/bin/python -m financial_brief.llm_config llm-config.json --test   # one small request per model
.venv-brief/bin/python -m financial_brief.server
```

Open http://localhost:8422. Two reports run at once; more uploads queue. Export JSON,
Markdown, a figures CSV, or print to PDF. Full setup and hosting: [SETUP.md](SETUP.md).

## Choose your models

`llm-config.json` lists the models you have (`llms`) and which one handles each job
(`tasks`). Providers: `openai` (OpenAI API), `link` (any OpenAI-compatible server:
vLLM, LM Studio, a gateway) and `ollama`. Everything local, with no API key:

```json
{
  "version": 1,
  "llms": {
    "local": {"provider": "link", "model": "your-served-model-id", "base_url": "http://127.0.0.1:8000/v1"}
  },
  "tasks": {
    "extract": "local", "extract_tables": "local", "recover_extract": "local",
    "write": "local", "review": "local", "answer": "local",
    "contract": "local", "month_inputs": "local"
  }
}
```

Or mix: a small model for simple extraction (`extract`, `month_inputs`) and a stronger
one for dense tables, writing, review and contract rules. The example file shows this
with GPT-5 nano and GPT-6 Luna. Hosted providers receive your document text and may
charge for it.

Keys stay in environment variables or key files, never in the JSON or the browser. The
config is read when each job starts, so edits apply to the next job without a restart.
Details: [LLM routing](docs/agent/LLM_ROUTING.md).

## What the checks prove, and what they don't

- Every quoted value must appear in the extracted source text; invented lines are rejected.
- Periods, units and scope come from the table headers they sit under.
- A second model pass checks material claims and displayed figures.
- For ABS deals, arithmetic and waterfalls are computed in code and compared line by line.

These checks do not audit the source or establish accounting accuracy. Image-only pages
and charts are not read (no OCR) and are reported as a coverage gap. Password-protected
PDFs need an unlocked copy.

Documents go only to the model endpoints in your config. Uploaded originals are deleted
after processing; reports expire after one hour by default.

## Command line and MCP

The original ABS tools still work without the browser app:

```sh
python3 -m reader.deal examples/santander-drive-2024-1-deal/* --backend ollama --model <model> --out deal.json
```

`mcp_server.py` exposes deal reports to Claude Code, Codex or Claude Desktop. Ask your
agent to "set this up as an MCP server" and it follows [AGENTS.md](AGENTS.md). See
[docs/ABS_READER.md](docs/ABS_READER.md) and [STARTUP.md](STARTUP.md).

## Development

```sh
.venv-brief/bin/python -m unittest discover -s tests -v   # offline; no model calls
```

- [Architecture](docs/agent/ARCHITECTURE.md)
- [Operations and troubleshooting](docs/agent/OPERATIONS.md)
- [Evaluation approach and limits](docs/agent/EVALUATION.md)
- [Development handoff](docs/agent/HANDOFF.md)

To add an example, add an entry to `financial_brief/examples/catalog.json` with a
`report_type` and `tags`.
