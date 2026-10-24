# Independent source-first review rubric

This is a small, qualitative product evaluation, not an audit opinion or statistical accuracy benchmark. Reviewers read the original documents before receiving app outputs. The app's own source checks and model verdicts are evidence to inspect, not substitutes for independent review.

## Procedure

1. Record document identity, source URL, publication date, reporting scope, page/word volume, and source-reading limitations.
2. Before reading the generated brief, list 6–10 material facts and 3–5 attribution/period/unit traps. Use original PDF pages or original article sections.
3. Run the exact original document(s) through the ordinary app upload endpoint. Preserve the submitted filenames, job settings, full generated JSON, and rendered/exported report.
4. Review every overview/highlight/risk, all headline cards and chart points, and a sample of the remaining table facts. Reopen the cited source page; a number occurring somewhere in a quotation is insufficient if the wrong column, entity, period or measure is attached.
5. Ask at least two follow-ups: one material question answerable from the source and one trap or unsupported request. Record the entire answer, citations and limits.
6. List supported claims, material omissions, unsupported/incorrect claims, and unjustified chart combinations. Distinguish hard errors from useful abstentions and stylistic preferences.
7. Propose the smallest fix that addresses a demonstrated issue. After a fix, rerun affected examples or replay preserved replies if the issue is purely deterministic. Retain before/after artifacts and disclose which evaluation was live versus replayed.

## Scoring (100 points)

| Dimension | Weight | Full-credit standard | Major deductions |
|---|---:|---|---|
| Factual correctness | 30 | Quoted values, signs, units, scales, periods and metric definitions agree with the source; chart values/grouping are faithful | Wrong table column; PAT versus attributable profit; consolidated versus standalone; quarter versus annual; currency/scale error; invented calculation |
| Material coverage | 25 | Covers the central financial story, cash/funding implications and major countervailing trends, consistent with the short-summary scope | Only promotional headline growth; omits segment/margin deterioration, debt/cash constraints, or an explicitly material operational/regulatory change |
| Attribution and scope | 15 | Issuer clearly named; subsidiaries/segments/peers distinct; actuals, management forecasts, analyst questions, non-GAAP metrics and audited accounts correctly labeled | Publisher named as issuer; subsidiary mistaken for group; question turned into management guidance; forecast presented as achieved result |
| Caveats and uncertainty | 15 | Conditions and footnotes that alter interpretation are preserved; gaps and unresolved checks are visible | Waiver/approval conditions omitted; no forecast caveat; silently substitutes absent financials; falsely implies audit/reconciliation or a verified waterfall |
| Source traceability | 10 | Each material statement/chart point has usable citations; evidence resolves to the original page/section and supports the attached label | Broken citation, unrelated quote, header/row context absent, misleading source/page label, or a missing-file omission hidden from coverage |
| Finance usefulness | 5 | A finance reader can quickly see company, period, core earnings/cash/balance-sheet drivers and relevant next questions; visuals add clarity | Long generic prose, undifferentiated number dump, decorative chart, missing period/unit captions, or overwhelming boilerplate |

Score each dimension from zero to its maximum. Report both the total and the specific evidence-based findings; a single total can hide important limitations.

## Critical-failure gates

A report cannot be called satisfactory while any material item below remains unresolved, regardless of total score:

- Wrong issuer or materially wrong period/entity/unit/sign.
- Invented earnings, ratios, forecasts, or a material causal conclusion unsupported by the document.
- Analyst question represented as approved management guidance.
- A model-generated waterfall passed off as verified despite failed structure or reconciliation.
- A chart combining incompatible entities/metrics/periods/scales in a way that changes the financial meaning.
- Material input omitted or truncated without clear disclosure.

An explicit abstention or Needs review flag is not a silent accuracy failure. It can still reduce usefulness or coverage. Distinguish `safe but incomplete`, `useful with caveats`, and `materially misleading`.

## Large-PDF implementation risks to inspect

These are code-review hypotheses, not claims that a particular generated report failed.

1. **Tables versus exact text:** `pypdf.extract_text()` flattens table cells. Fixed 10,000-character chunks may split table headers from rows. Source matching proves a token appears, not the correct period/entity/column association. A faithful row quote can lack the table's unit or fiscal header.
2. **Fiscal-period metadata:** `clean_metadata()` requires metadata tokens to occur within the same fact quote. A table labeled FY25 outside the row can lose its period/unit. Normalizing FY25 to 2025 also loses that explicit-token match. This is safer than guessing, but leaves less useful tables/charts unless the extractor includes the relevant header context in an exact quote.
3. **Chart scope:** Current chart grouping requires a calendar year `20xx`, identical source section/label/unit and explicit currency/percentage. This intentionally suppresses ambiguous comparisons, but Indian FY25/FY24 figures and quarter comparisons will often have no chart. Do not replace fiscal years with calendar years just to force one. Crore/Indian-comma formatting and parentheses/sign handling deserve direct tests.
4. **Review coverage:** The model review checks all draft prose and only the first six numerical facts. Later table facts or chart candidates may have only lexical source matching, not a semantic label/period review. A visible review status or reviewing selected chart/table facts would make the limits clearer.
5. **Materiality:** Extracting up to 14 facts from each chunk can create many true but low-value facts. The earliest chunks can dominate the first six cards and first 40 table rows. A 350–500-word brief needs a source-grounded materiality selection so conglomerate segment offsets and funding risks survive.
6. **Issuer selection:** The first valid company proposal per file wins. PDF covers may include stock exchanges, auditors, investment-bank publishers and subsidiaries. Exact occurrence of a name does not establish it is the primary issuer. Repeated headers/legal title evidence should outweigh incidental cover-page entities.
7. **Multi-file identity:** Generic `read_sources()` currently uses `path.name`. Two uploaded subfolders with the same basename can collapse issuer grouping, deduplication and chart source labels. Preserve a document ID or relative path rather than relying only on basename.
8. **Numeric token checks:** `numbers()` strips commas and treats numeric tokens as a set; signs, semantic roles and scale are not protected by that check alone. The separate semantic review must catch wrong-sign/wrong-measure claims. New calculations should remain in explicit code with traceable inputs.
9. **Forward-looking language:** An earnings-call transcript interleaves analyst questions with management responses. Retrieval or extraction can capture a proposed target without its denial in the following answer. HDFC's 2% ROA question is a concrete adversarial example.
10. **Summary fallback:** When prose review rejects everything, the overview falls back to the first two fact quotations. That preserves source text but is not necessarily a coherent financial summary; disclose the fallback and do not score it as an analyst-quality synthesis merely because it is quoted.

## Example-specific priority tests

- Reliance FY25: group gross revenue vs revenue from operations; PAT including associates/JVs; consumer growth versus O2C margin pressure; capex excludes spectrum; annual versus quarterly figures.
- HDFC Q4FY25 call: CD-ratio repair and expected FY27 normalization; margin/funding tradeoffs; no declared 2% ROA target or specific NIM outlook; analyst questions versus management guidance.
- Zomato/Eternal: food-delivery versus Blinkit economics; adjusted EBITDA versus reported profit; order value versus revenue; stores, investments and cash; historical naming and reporting scope.
- Zerodha: private-company management commentary versus audited consolidated accounts; one-off versus recurring income; regulatory headwinds; segment/product timing and attribution.
- Netflix 2002: historical DVD subscription business, not modern streaming; losses versus cash generation; dollars in thousands versus per-share amounts; permissions encryption versus unreadable content; 86-page coverage.
- Auto-loan deal: monthly pool/note identities, same-month tape reconciliation, contract rule completeness, class-payment comparisons and explicit failed checks.
