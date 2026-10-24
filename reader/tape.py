"""Loan tape (SEC ABS-EE asset XML, or a CSV with the same field names) -> pool statistics.

The tape's total ending balance should equal the servicer report's ending pool balance for the same month; the
difference is shown, not assumed away ("close" = within 0.01%, typical of timing between tape and report).
"""
import csv
import math
import xml.etree.ElementTree as ET

BAL, RATE, FICO, TERM = ("reportingPeriodActualEndBalanceAmount", "reportingPeriodInterestRatePercentage",
                         "obligorCreditScore", "remainingTermToMaturityNumber")


def rows(path):
    if path.lower().endswith(".xml"):
        for _, el in ET.iterparse(path):
            if el.tag.endswith("}assets") or el.tag == "assets":
                yield {c.tag.split("}")[-1]: (c.text or "") for c in el}
                el.clear()
    else:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            yield from csv.DictReader(f)


def num(x):
    try:
        value = float(str(x).replace(",", ""))
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def summary(path):
    n, total, period, dq, wsum = 0, 0.0, None, {}, {RATE: [0.0, 0.0], FICO: [0.0, 0.0], TERM: [0.0, 0.0]}
    total_assets, missing_delinquency_assets = 0, 0
    for r in rows(path):
        total_assets += 1
        if BAL not in r:
            return {"error": "not a loan tape with ABS-EE field names (needs reportingPeriodActualEndBalanceAmount)"}
        b = num(r.get(BAL)) or 0.0
        period = period or r.get("reportingPeriodEndingDate")
        if b <= 0:
            continue  # paid off or charged off this month
        n += 1
        total += b
        for k in wsum:
            v = num(r.get(k))
            if v is not None:
                wsum[k][0] += v * b
                wsum[k][1] += b
        days = num(r.get("currentDelinquencyStatus"))
        if days is None or days < 0:
            bucket = "unknown"
            missing_delinquency_assets += 1
        else:
            bucket = "current" if days < 30 else "30-59" if days < 60 else "60-89" if days < 90 else "90+"
        dq[bucket] = dq.get(bucket, 0.0) + b
    wa = {k: round(s / w, 4) if w else None for k, (s, w) in wsum.items()}
    if wa[RATE] is not None and wa[RATE] < 1:
        wa[RATE] = round(wa[RATE] * 100, 2)  # ABS-EE prints rates as fractions (0.1213 = 12.13%)
    return {"period_end": period, "loans": n, "total_assets": total_assets,
            "excluded_nonpositive_assets": total_assets - n,
            "missing_delinquency_assets": missing_delinquency_assets,
            "missing_delinquency_balance": round(dq.get("unknown", 0.0), 2),
            "balance": round(total, 2), "wa_rate_pct": wa[RATE],
            "wa_credit_score": wa[FICO] and round(wa[FICO], 1), "wa_remaining_term": wa[TERM] and round(wa[TERM], 1),
            "delinquency_balance": {k: round(v, 2) for k, v in sorted(dq.items())}}


def against_report(tape, rec):
    """Tape balance vs the servicer report's ending pool balance (same month)."""
    pool = rec.get("pool_balance_ending")
    if pool is None or tape.get("balance") is None:
        return None
    diff = round(tape["balance"] - pool, 2)
    status = "match" if abs(diff) <= 1.0 else "close" if pool and abs(diff) <= 0.0001 * pool else "differs"
    return {"report_pool_balance": pool, "difference": diff, "status": status}
