You are turning a securitization contract's priority of payments into a machine-readable spec.
Read the contract excerpt (the payments section plus the definitions it relies on) and write ONE JSON object:

{
 "terms": {"note_rates_pct": {"<class id>": <coupon in percent>, ...}, "other": "<anything else you relied on>"},
 "definitions": {"<name>": "<expression>", ...},
 "steps": [{"id": "<clause number, e.g. iii>", "pay": "<what is paid>", "kind": "fee|interest|principal|reserve|residual",
            "amount": "<expression>"}, ...],
 "principal_order": [["<class id>"], ["<class id>", "<class id paid pro rata with it>"], ...]
}

Rules
- Class ids are identifier-safe: A1, A2a, A2b, A3, A4, B, C, D (no dashes).
- Expressions use only numbers, names, + - * /, parentheses, min(...), max(...). No other functions or code.
- Expressions may use these inputs, which come from that month's servicer report:
    bal_<class>            note balance of each class on the day before the distribution date
    pool_begin             pool balance at the start of the collection period just ended
    pool_end               pool balance at the end of the collection period just ended
    pool_cutoff            pool balance as of the cutoff date (initial pool)
    available_funds        cash available for the waterfall this distribution date
    unreimbursed_advances, capped_expenses, uncapped_expenses, reserve_deficiency   (amounts due, usually 0)
    reserve_balance        cash in the reserve account before this date's deposits
  and any name you define in "definitions" (define a name before using it). Use only these inputs and your own
  definitions: trustee, owner trustee, reviewer and other fees or expenses are capped_expenses / uncapped_expenses.
- Define interest for each class as int_<class> (30/360: balance x coupon / 100 / 12 unless the contract says otherwise),
  and the servicing fee as servicing_fee, from the contract's own terms.
- Translate every "Distributable Amount" or target definition into an expression exactly as the contract defines it.
- steps: every clause of the priority of payments in order. The last step (remaining funds) has kind "residual".
- If something in the contract is ambiguous (e.g. two different rates printed for one class), choose what the
  contract defines as the note's interest rate and say what you resolved in terms.other.
Write the JSON only.
