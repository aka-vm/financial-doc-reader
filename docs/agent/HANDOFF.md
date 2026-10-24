# Handoff — October 2026 update

This is the continuation map for the Ledger work. Read [AGENTS.md](../../AGENTS.md)
first and use the original user conversation for any later corrections.

## Product decisions

- Primary browser app: Ledger on port 8422, alongside original ABS CLI/MCP interfaces.
- Warm light, dark and system/auto themes; saved selection and light PDF printing.
- Author/portfolio/repository links at the top; small UI changes rather than a redesign.
- Exactly six random examples visible; label is **“6 random”**. Shuffle replaces them.
  Keep the 50-example library behind the widget, not a 50-card list.
- Use substantial public documents, including Indian brands (Eternal/Zomato, Zerodha,
  Reliance, HDFC, TCS, Wipro), global company disclosures and complete SEC/loan data.
- Folder/ZIP intake, async report/question jobs, two concurrent report slots, queued work,
  source-linked tables/optional graphs and JSON/Markdown/CSV/PDF exports.

## Model decisions

The live ignored registry uses `nano` = GPT-5 nano and `luna` = GPT-6 Luna.
Simple scan/monthly inputs use nano; dense tables, low-yield recovery, writing,
semantic review, questions and contract rules use Luna. Both can be replaced with
local entries through the task map, without changing code or requiring an OpenAI key.
The checked-in example is not permission to choose a paid provider for a new user.

Independent development reviews use agy with Gemini Flash coordinating. GPT-OSS may
return a Markdown review even when JSON was requested; preserve it rather than claim
it is a successful structured result. Other reviewer accounts can hit quota; record
fallbacks accurately. Never silently call a different provider/model than configured.

## Where to continue

- Server and job lifecycle: `financial_brief/server.py`.
- LLM registry: `financial_brief/llm_config.py`, `llm-config.example.json`.
- Financial extraction/review: `financial_brief/engine.py`.
- Tables/charts/headline selection: `visuals.py`, `selection.py`, `static/data-views.js`.
- Browser/export/theme: `static/app.js`, `exports.js`, `theme.js`, `index.html`, `style.css`.
- Original arithmetic, waterfall, tapes: `reader/`.
- Independent review CLI: `financial_brief/review_examples.py`.

For current live-run findings and exact model responses, inspect ignored
`out/example-review/` if present. Earlier mini/nano+5.6-Luna runs are intermediate
artifacts, not evidence of the final GPT-6 Luna configuration. Use EVALUATION.md to
regenerate and review results instead of copying an old score.

## Important remaining limits

No OCR is performed for image-only charts/tables. Generic briefs are not accounting
reconciliations; a model review does not independently audit a statement. Contract
formulas/inputs may remain unresolved and must remain visibly flagged. Only compatible
explicit comparisons should chart. Private session/report artifacts must not be pushed.

Example cards carry up to three tags (report type, topic and region). The six-card
selection samples report types equally before repeating a type, so the larger SEC
servicer collection does not dominate. The library includes full annual reports,
earnings releases, management updates, earnings calls, proxy statements, servicer
reports and complete ABS bundles. Add examples through `financial_brief/examples/catalog.json`
with `report_type` and `tags`; no extra service or model call is required.

Latest continuation: quota errors were cleared for OpenAI and both configured models
passed connection checks. Real corporate jobs completed. agy reviews used Gemini
fallbacks because GPT-OSS/Sonnet accounts still reported quotas. See EVALUATION.md for
honest pre-repair scores and the bounded exact-source header repair. The rubric now
lives in REVIEW_RUBRIC.md so a fresh checkout can use the review runner.
