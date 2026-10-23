You are extracting figures from one monthly servicer report of an auto-loan securitization.
Return ONE JSON object matching the schema. Copy what the report prints; never compute.

GENERAL RULES
- Numbers exactly as printed, as plain JSON numbers (no $ or commas). A value in parentheses is negative.
- A dash ("—", "-") in a row that exists means 0. Use null only when the report has no such line at all.
- Percentages in percent units as printed ("2.8329 %" -> 2.8329).
- Dates as YYYY-MM-DD. If the collection period is given only as a month, use its first and last day.
- Use this period's figures: not original, prior-period or cumulative columns unless the field asks for them.
- If the report prints two different values for the same field, use the one in the main calculation and add the
  field name to "ambiguous_fields".

FIELDS
- pool_balance_beginning / pool_balance_ending: receivables pool principal balance at start / end of the period.
- initial_pool_balance: pool balance at the cut-off / closing date.
- receivables_count_ending: number of receivables outstanding at period end.
- Losses: use the report's net-loss calculation for THIS period (not cumulative):
  - gross_charge_offs: principal of receivables that defaulted / were charged off / were liquidated this period,
    before any recoveries: the amount a net-loss calculation starts from. It may be printed outside the loss section.
    null if the report prints only net charge-off figures; never fill it with a net figure.
  - recoveries_components: every amount the calculation subtracts from gross charge-offs (e.g. liquidation proceeds
    and recoveries, if printed as separate lines). [] if none printed.
  - recoveries: the single line if there is exactly one subtracted amount; otherwise null.
  - net_losses: this period's net loss as printed (exact, not rounded; negative if a net recovery).
- cumulative_net_losses: cumulative net losses in dollars since the cut-off date, as of period end.
- cumulative_net_loss_pct: cumulative net losses as % of the initial pool, current period.
- delinquency: each delinquency bucket (e.g. 31-60, 61-90, 91-120, 121+ days) with count and balance; skip totals.
- servicing_fee: the servicing fee paid to the servicer this period (not a larger "strip" shared with others).
- reserve_account_ending: reserve account balance after this period's distributions.
- overcollateralization_ending: overcollateralization amount at period end, if printed (not a target amount and
  not a yield supplement overcollateralization / YSOC amount).
- excess_to_residual: cash released at the very end of the waterfall to the certificateholder / residual holder /
  seller / depositor. Never a principal payment, even if a principal line is labelled "excess".
- notes: one entry per note class printed (including paid-off classes as zeros): beginning_balance, ending_balance,
  interest_paid, principal_paid on this distribution date.
