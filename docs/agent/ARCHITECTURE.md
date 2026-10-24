# Architecture

`financial_brief.server:create_app()` is the primary browser app (Flask, port 8422).
There is no frontend build. HTML/CSS/JS are served from `financial_brief/static/`.
`app.py`/`reader/ui.html` and `mcp_server.py` are the original ABS web/MCP interfaces.

## Browser processing

1. A signed `ledger_session` cookie owns each report. Writes require the same-origin
   `X-Brief-Request` header. No CORS access is granted.
2. Multipart uploads are saved privately. Six reports may be admitted; a bounded
   thread pool processes two concurrently by default. Status is queued/running/done/error.
3. `financial_brief.bundles` preserves safe relative paths, expands one ZIP level,
   rejects traversal/symlinks/collisions and oversized archives, and removes duplicate
   TXT exports when the HTML original exists. Hidden/metadata files are skipped.
4. Financial brief mode calls `engine.build`; ABS mode calls `bundles.build_deal`
   and the original `reader.deal.build`.
5. Model/parse errors become report errors or explicit ABS review items. Originals
   are removed in `finally`. Atomic JSON snapshots live in `BRIEF_DATA` and expire.
6. The browser polls status. Follow-up answers also run as background jobs. Exports
   are built from the displayed report in the browser.

## Reading and checking

- `reader.convert`: rebuilds HTML grids; PDF reading permits an empty password.
  PDF layout is used only if it preserves original numeric tokens; otherwise plain
  extraction is retained. `fonttools` supports older embedded fonts.
- `financial_brief.engine`: isolated decoding, overlapping source sections, exact
  quotation/value matching, header context, subject identity, synthesis and context review.
- `financial_brief.selection`: material headline figures rather than first-seen identifiers.
- `financial_brief.visuals`: conservative same-source, same-metric/unit/period comparisons.
  No ratios, growth rates, currencies or scales are invented to force charts.
- `reader.checks`, `reader.contract`, `reader.tape`: ABS arithmetic, formula validation,
  waterfall execution and loan-pool aggregation. Missing delinquency is Unknown.

## LLM routing

`financial_brief.llm_config` validates named entries and task-to-key mappings.
A ContextVar assigns each job its own immutable routing snapshot; threads cannot
change each other's selected models. The backend dispatch in `reader.backends`
supports OpenAI Responses, compatible chat APIs and native Ollama. A new job reloads
the registry; a running job retains its revision.

## Main APIs

- `GET /healthz`: web status and safe task/model metadata.
- `GET /api/examples`, `GET /examples/<allowlisted-name>`: 50 public source examples.
- `POST /api/briefs`: accept upload/mode; return a job ID with HTTP 202.
- `GET /api/briefs/<id>`: owner-scoped progress/result.
- `POST /api/briefs/<id>/ask`, `GET /api/briefs/<id>/answers/<answer-id>`: async questions.
- `DELETE /api/briefs/<id>`: delete a finished, owned report.

Data/storage is intentionally single-process. Multiple Gunicorn worker processes
would create independent gates and recovery loops against the same directory.
