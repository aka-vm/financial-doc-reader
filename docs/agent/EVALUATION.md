# Evaluation and source fidelity

The ordinary test suite makes no hosted model requests:

```sh
python3 -m reader.selftest
.venv-brief/bin/python -m unittest discover -s tests -v
```

It covers source matching, headers/units, PDF permissions/layout, job ownership,
queue/concurrency, archives, routing/credentials, exports/data-view helpers and ABS
structure/tape handling. Browser QA is separate and requires Playwright plus Chromium;
these are development tools, not production dependencies.

## Real-source review

The user requested independent **agy** reviews with Gemini Flash coordinating.
Use `agy models` to verify current IDs and account access. The repeatable runner is:

```sh
.venv-brief/bin/python -m financial_brief.review_examples \
  --phase my-review --reports out/example-review/app-runs \
  --examples reliance zerodha zomato hdfc
```

The parent assigns independent finance/source roles, children receive complete
extracted source text plus the actual app JSON, and Gemini Flash adjudicates claims
against the source. Record the actual reviewer model, quota/format fallback, model
usage, limitations and verdict. Do not use session subagents in place of this workflow.
agy is optional and requires its own setup/login; do not require it just to run Ledger.

Read the source before inspecting the output. Inspect issuer, period, group/segment,
reported/adjusted measures, signs, scales, conditions and speakers. An analyst question
is not management guidance. A value present in a quote can still refer to the wrong
column. Also inspect material omissions and whether charts combine incompatible data.

A reviewer may itself make an error (for example mixing annual margin differences
with a quarterly basis-point column). Scores are not truth or an audit opinion.
Preserve concrete source citations and distinguish a missing fact from a false claim.

## Improvements prompted by real examples

- Preserve original PDF numeric tokens; use plain extraction if layout splits digits.
- Retain table-heading context with each extracted row and display that evidence.
- Select material figures rather than arbitrary filing IDs/first-seen numbers.
- Require a verdict for every requested claim and figure through a closed review schema.
- Route dense tables/low-yield extraction to the configured heavier model.
- Keep fiscal/calendar and annual/quarterly labels separate in comparisons.
- Preserve ambiguous `Rs` as printed rather than assuming INR; never convert currencies
  or invent annual figures to force charts.
- Label image-only pages/HTML charts as coverage limitations.
- Validate executable contract structure before running or asking for repairs.
- Keep unknown delinquency separate from Current and distinguish active loans from rows.

## Artifacts and limits

Live run reports, source-first baselines, screenshots and raw agy responses are local
under ignored `out/example-review/`; they may not exist in a fresh clone. Public source
assets/provenance are under `financial_brief/examples/real/` and catalogued in
`financial_brief/examples/catalog.json`. Generated reports may contain private uploads
and are not committed indiscriminately.

Historical Qwen/ABS and earlier small-fixture results remain historical; do not present
them as performance measurements for the current nano/Luna configuration. The 50-file
library has intake/source checks; a few representative examples were run live. It is
not a 50-case statistical accuracy benchmark. Exact past OpenAI spend cannot be
reconstructed from retained JSON alone because original usage fields were not logged.

## Latest live checks (24 October 2026)

The configured GPT-5 nano / GPT-6 Luna endpoints both passed live JSON connection
checks. Browser-submitted Reliance, Zerodha and Eternal examples completed with the
configured task map (30, 26 and 96 sourced facts respectively before the final header
repair). Eternal produced a source-linked comparison chart; the other two abstained.

agy Gemini Flash High adjudicated these outputs: Zerodha 85/100 (acceptable), Eternal
82/100 (acceptable), Reliance 69/100 (not acceptable due to material omissions).
These are qualitative reviewer opinions, not measured accuracy. GPT-OSS and Sonnet
were requested but their accounts reported individual quotas; Gemini Flash Medium
performed the fallback child reviews with separate assigned roles. This run therefore
does **not** establish agreement across independent model families.

Confirmed improvements after these reviews: exclude auditor-scope footnotes and
unmaterial line items from headline selection; exclude narrative values whose only
digit belongs to a name (e.g. KGD6) from numeric tables; distinguish product age from
reporting periods; keep decline direction in labels without inventing printed signs.
A table-header failure was traced to the model joining separated real header lines.
The reader now restores the exact enclosing source span only when all lines occur in
order within 3,000 characters. Invented lines remain rejected. On the saved Jio
section this restored 12 source-matched facts versus one previously, without changing
any value. The above scores predate these changes; do not present them as a benchmark
of the repaired version. Image-only content and incomplete material coverage remain
real limitations. The ordinary suite now has 64 passing tests plus the original ABS
self-test; separate browser QA covers tags, balanced six-card sampling, themes,
exports, mobile layout and stale sessions.

A further regression fix lets prose cite a reporting year found in its verified
column-heading evidence, rather than requiring that year to be repeated inside the
numeric row quotation. Unsupported years still fail the numeric guard.
