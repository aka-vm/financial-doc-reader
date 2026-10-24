# Development evaluation — 24 October 2026

Model: `sakamakismile/Qwen3.8-27B-MTP-NVFP4`, served as `qwen3.8` through the user's
existing OpenAI-compatible API. Temperature zero and structured JSON on every call.
Version hashes, per-case metrics, and dependency versions are in [results.json](results.json).

| Check | Test split | Validation split |
| --- | ---: | ---: |
| Briefs generated | 8/8 | 4/4 |
| Selected target values present in accepted facts | 23/24 | 13/13 |
| Follow-up answer checks, after bounded repair | 8/8 | 4/4 |
| Claims satisfy citation/numeric guards | 8/8 briefs | 4/4 briefs |
| PDFs fit in one or two A4 pages | 8/8 | 4/4 |
| No horizontal overflow at 390px | 8/8 | 4/4 |

The corpus contains ten explicitly fictional disclosures and two real bundled ABS
reports. It covers earnings, credit covenants, negative values, fund returns, bank
capital, conflicting disclosures, prompt injection, insurance, INR/crore, and going
concern disclosures. The splits were defined before the runs but both were inspected
and rerun during development. This is a regression set, not an independent benchmark.

Across the cases, 18 candidate facts/cards/statements were withheld by source,
numeric, or context checks; eight of those were draft claims rejected by model
context review. Two follow-up answers required one rewrite after source checks:
one included an uncited loss amount and one calculated an unstated percentage-point
change. The rewrites were subjected to the same guards. Recorded replies include
these attempts and can be replayed without model access.

The omitted target value was CarMax's beginning pool balance, `488,411,599.98`.
The general extractor selects a limited set of facts per section; it does not claim
exhaustive extraction. The original specialist ABS pipeline, tested separately on
two CarMax reports, matched **106/106** reference numeric figures with **zero flags**.
Its existing no-model self-test also passed across six bundled reports.

Seventeen automated tests passed, including 60 generated currency/scale/negative-value
combinations, PDF page ranges, encrypted/blank PDFs, decoder isolation, full text
coverage, source guards, metric-context rejection, bounded answer repair, upload
limits, session isolation, report deletion, and expiry. An actual browser upload
generated a Northstar brief, answered its cash-flow question with the inventory and
collections explanation, opened citations, and printed to two pages. A separate
mocked browser run checked desktop/mobile layout, downloads, and deletion.

Important limits: substring/value coverage does not establish that a figure has the
correct financial interpretation. Answer keyword/period checks are smoke checks,
not semantic grading. The second context pass uses the same model, so it is not
independent verification. No generic accounting reconciliation or OCR is included.
Long, scanned, complex real-world financial documents need further evaluation.

Replay the saved model replies:

```sh
.venv-brief/bin/python -m financial_brief.evaluate --split all \
  --out /tmp/ledger-replay --replay-from financial_brief/eval/recordings
```

Run a new live evaluation by omitting `--replay-from`. Raw recordings contain only
the fictional examples and the repository's public ABS documents.
