# Servicer Report Reader

Turns a monthly auto-loan ABS servicer report (the 10-D exhibit trusts file on SEC EDGAR) into one standard set of
figures: pool balances, charge-offs, recoveries, net and cumulative losses, delinquency buckets, servicing fee,
reserve account, overcollateralization and every note class's balances and payments.

Every figure is checked with arithmetic the report has to satisfy. A figure that fails a check comes back
**flagged with the reason**, so nothing doubtful is silently passed on.

A small project I put together in a few hours. Tested with **Qwen 3.8 27B** running on my own GPU box.

![drop a report, get checked figures](docs/screenshot.png)

## Why a local model

Servicer reports, and the loan data behind them, are often confidential. Running an open model on your own machine
or server keeps the documents on your hardware, costs nothing per page, and stays reproducible: same model
version, temperature 0, a fixed output schema.

A mid-sized open model doesn't read every report perfectly. The checks are what make it usable: most of its
mistakes come back as flags instead of passing silently, so a person only needs to look at the flagged figures.

## How it works

1. **Convert.** HTML tables are rebuilt as a real grid (merged cells, multi-row and grouped headers), and each number
   is written out with its row and full column path, e.g.
   `Net Credit Losses :: Current Period Only = $442,621.32 ; Cumulative > Current Period = $5,840,372.73`.
   Flattened tables are the most common way a model ends up reading the wrong column.
2. **Read.** The model fills a fixed JSON schema (constrained output) and copies figures as printed.
3. **Fix in code, not by the model.** Recoveries printed as several lines are summed in code, and a whole-dollar copy
   is replaced by the exact figure when the report prints it with cents elsewhere.
4. **Check.** Issuer-independent identities: each note class rolls forward (beginning - principal = ending), pool
   minus notes vs overcollateralization, gross - recoveries = net loss, cumulative loss % = cumulative losses /
   initial pool, notes never exceed the pool, a period figure can't be most of the cumulative one, every printed
   figure must actually appear in the report, and, across months of one trust, balances and the initial pool carry
   over.

## Results

Qwen 3.8 27B (4-bit), one pass per report, no retries. "Wrong, flagged" means the checks caught it;
"wrong, not flagged" is a silent error.

| reports | issuers | values | correct | wrong, flagged | wrong, not flagged |
|---|---|---|---|---|---|
| 15 development reports | 5 | 780 | 778 (99.7%) | 2 | **0** |
| 16 test reports from issuers never used while building | 4 | 686 | 678 (98.8%) | 8 | **0** |

Answer keys: rule-based parsers for the development reports; for the test reports, the values two reference models
agree on, with every disagreement checked by hand against the report.

## Run it

Python 3.10+, no required packages (`pip install pypdf` for PDF reports, `pip install anthropic` for the Anthropic
backend). Example reports are in Git LFS: `git lfs install && git lfs pull`.

```bash
python3 -m reader.selftest          # no model needed: converter + checks on the examples
```

Pick where the model runs:

| | backend | example |
|---|---|---|
| 1. Local model (Ollama) | `ollama` | `--backend ollama --model <qwen model>` |
| 2. Your own server, by link (vLLM, llama.cpp, LM Studio) | `link` | `--backend link --url http://my-gpu-box:8000/v1 --model qwen3.8` |
| 3. The coding agent you already use | `codex`, `claude-code`, `gemini-cli` | `--backend codex` |
| 4. A hosted model with your API key | `anthropic`, `openai`, `gemini` | `ANTHROPIC_API_KEY=... --backend anthropic` |

Options 3 and 4 send the report to an outside service; 1 and 2 keep it on your hardware.

```bash
# command line: one JSON per report (several months of one trust are also checked against each other)
python3 -m reader.extract examples/carmax-2024-1__2026-07-31.htm examples/carmax-2024-1__2026-08-31.htm \
    --backend ollama --model <model> --out out/

# web page: drag reports onto http://localhost:8420
python3 app.py --backend ollama --model <model>
```

Using a coding agent? Point it at [AGENTS.md](AGENTS.md); it walks through the setup.

## Files

```
app.py              the drop-in page (standard library HTTP server)
reader/convert.py   report file -> model-readable text (table grid rebuild)
reader/prompt.md    field definitions given to the model
reader/schema.json  the output schema
reader/backends.py  Ollama, OpenAI-compatible link, agent CLIs, hosted APIs
reader/checks.py    the arithmetic checks
reader/extract.py   convert -> read -> fix -> check (CLI)
examples/           six public servicer reports (Git LFS) with checked answers
```

## Limits

Built for US auto-loan ABS servicer reports (EDGAR 10-D exhibits). PDFs need a text layer (no OCR). When a report
prints two different loss calculations for the same month and the model copies the other one consistently, the
arithmetic can't tell; the prompt asks the model to mark such fields as ambiguous, and it doesn't always.
