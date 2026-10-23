"""Arithmetic checks that hold for any auto-loan ABS servicer report. A value that fails one is flagged for review,
never silently trusted. Nothing here is tuned to one issuer.

issues(rec, source_text, prev=None) -> {path: reason}; prev = last month's record for the same trust.
paths look like "pool_balance_ending", "notes[A-3].principal_paid", "delinquency[31-60].balance".
"""
import re

MONEY_TOL = 1.0  # some issuers print whole dollars


def cls(name):
    return re.sub(r"CLASS|NOTES?|\s", "", str(name).upper())


def bucket(label):
    n = [int(x) for x in re.findall(r"\d+", str(label))]
    if not n:
        return str(label)
    return "121+" if n[0] >= 120 else f"{n[0]}-{n[1]}" if len(n) > 1 else str(n[0])


def source_numbers(text):
    out = set()
    for tok in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            out.add(round(float(tok.replace(",", "")), 2))
        except ValueError:
            pass
    return out


def leaves(rec):
    """(path, value) for every scalar the schema defines."""
    for k, v in rec.items():
        if k == "notes":
            for n in v or []:
                for f, x in n.items():
                    if f != "class":
                        yield f"notes[{cls(n.get('class'))}].{f}", x
        elif k == "delinquency":
            for d in v or []:
                for f in ("count", "balance"):
                    yield f"delinquency[{bucket(d.get('bucket'))}].{f}", d.get(f)
        elif k == "recoveries_components":
            for i, x in enumerate(v or []):
                yield f"recoveries_components[{i}]", x
        elif not isinstance(v, (list, dict)):
            yield k, v


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def finalize(rec):
    """Recoveries printed as several subtracted lines are listed by the model and summed here (code computes, not the model)."""
    comps = [x for x in rec.get("recoveries_components") or [] if num(x)]
    if comps and all(x <= 0 for x in comps):
        comps = [-x for x in comps]  # every line printed in parentheses = a deduction, i.e. a positive recovery
    if rec.get("recoveries") is None and comps:
        rec["recoveries"] = round(sum(comps), 2)  # mixed signs (proceeds less expenses) sum as printed
    if num(rec.get("recoveries")) and rec["recoveries"] < 0:
        rec["recoveries"] = -rec["recoveries"]  # recoveries are an amount subtracted; the parentheses are the sign
    return rec


def exact(rec, source_text):
    """A figure copied in whole dollars when the report also prints it with cents ("579,123" and "579,123.42") is
    replaced by the exact printing: the model found the figure, code picks the precision. Counts are left alone."""
    cents = {}
    for tok in re.findall(r"\d[\d,]*\.\d\d(?!\d)", source_text):
        v = float(tok.replace(",", ""))
        cents.setdefault(int(v + 0.5), set()).add(v)

    def fix(k, x):
        if k in ("receivables_count_ending", "count") or not num(x) or x != int(x) or abs(x) < 1000:
            return x
        m = cents.get(int(abs(x)), set())
        return (next(iter(m)) if x > 0 else -next(iter(m))) if len(m) == 1 else x

    for k, v in rec.items():
        if isinstance(v, list):
            rec[k] = [{kk: fix(kk, vv) for kk, vv in x.items()} if isinstance(x, dict) else fix(k, x) for x in v]
        else:
            rec[k] = fix(k, v)
    return rec


def issues(rec, source_text, prev=None):
    out = {}
    computed = {"recoveries"} if rec.get("recoveries") is None and rec.get("recoveries_components") else set()
    rec = finalize(dict(rec))
    nums = source_numbers(source_text)
    # 1. provenance: a non-zero number that never appears in the report was not read from it
    for path, x in leaves(rec):
        if path in computed:
            continue  # summed by code from printed components (each component is checked itself)
        # compare magnitudes: a net recovery printed as "(64,802.87)" is stored as -64802.87
        if num(x) and x and round(abs(float(x)), 2) not in nums and round(abs(float(x)) * 100, 2) not in nums:
            out[path] = f"{x} does not appear in the report"
    notes = [n for n in rec.get("notes") or [] if isinstance(n, dict)]
    # 2. each class rolls forward: beginning - principal = ending
    for n in notes:
        b, e, p = n.get("beginning_balance"), n.get("ending_balance"), n.get("principal_paid")
        if all(num(v) for v in (b, e, p)) and abs(b - p - e) > MONEY_TOL:
            c = cls(n.get("class"))
            for f in ("beginning_balance", "ending_balance", "principal_paid"):
                out.setdefault(f"notes[{c}].{f}", f"class {c}: {b} - {p} != {e}")
    # 2a. amortizing notes never grow during a month
    for n in notes:
        b, e = n.get("beginning_balance"), n.get("ending_balance")
        if num(b) and num(e) and e > b + MONEY_TOL:
            out.setdefault(f"notes[{cls(n.get('class'))}].ending_balance", f"ending {e} > beginning {b}")
    # 2b. a month of interest is a small fraction of the balance (36%/yr would already be absurd for an ABS note)
    for n in notes:
        b, i = n.get("beginning_balance"), n.get("interest_paid")
        if num(i) and num(b) and i > 0.03 * b:
            out.setdefault(f"notes[{cls(n.get('class'))}].interest_paid", f"interest {i} > 3% of balance {b}")
    # 2c. servicing fees run ~1-2%/yr of the pool, so well under 0.5% a month
    fee, pb0 = rec.get("servicing_fee"), rec.get("pool_balance_beginning")
    if num(fee) and num(pb0) and fee > 0.005 * pb0:
        out.setdefault("servicing_fee", f"fee {fee} > 0.5% of pool {pb0}")
    # 2d. the residual holder gets the month's excess spread (well under 1% of the pool); a value of several percent
    #     is a total line (e.g. "Total Distribution Amount"), not the residual
    ex = rec.get("excess_to_residual")
    if num(ex) and num(pb0) and pb0 > 0 and ex > 0.04 * pb0:
        out.setdefault("excess_to_residual", f"{ex} is {100 * ex / pb0:.1f}% of the pool; residual cash is usually <1%")
    # 3. overcollateralization = pool - notes. Deals with a yield-supplement OC compute it on an *adjusted*
    #    (smaller) pool, so OC may fall short of pool - notes, but never exceed it, and never by much.
    pe, pb, oc = rec.get("pool_balance_ending"), rec.get("pool_balance_beginning"), rec.get("overcollateralization_ending")
    if num(pe) and num(oc) and notes:
        s = sum(n.get("ending_balance") or 0 for n in notes)
        gap = pe - s - oc
        if gap < -MONEY_TOL or gap > 0.10 * pe:
            for path in ["pool_balance_ending", "overcollateralization_ending"] + [f"notes[{cls(n.get('class'))}].ending_balance" for n in notes]:
                out.setdefault(path, f"pool {pe} - notes {s:.2f} != OC {oc}")
    # 3b. notes are backed by the pool: their opening total can't exceed the opening pool balance
    if num(pb) and notes:
        s0 = sum(n.get("beginning_balance") or 0 for n in notes)
        if s0 > pb + MONEY_TOL:
            for n in notes:
                out.setdefault(f"notes[{cls(n.get('class'))}].beginning_balance",
                               f"opening notes {s0:.2f} exceed opening pool {pb}")
    # 4. the pool amortizes
    if num(pe) and num(pb) and pe >= pb:
        out.setdefault("pool_balance_ending", f"ending {pe} >= beginning {pb}")
        out.setdefault("pool_balance_beginning", f"ending {pe} >= beginning {pb}")
    # 4b. like an analyst eyeballing the month: a pool doesn't lose 30% in a month (outside a clean-up call)
    if num(pe) and num(pb) and pb > 0 and pe < 0.7 * pb:
        out.setdefault("pool_balance_ending", f"pool fell {100 * (1 - pe / pb):.0f}% in one month")
    # 5. delinquent balances and counts fit inside the pool
    for d in rec.get("delinquency") or []:
        b = bucket(d.get("bucket"))
        if num(d.get("balance")) and num(pe) and d["balance"] > pe:
            out.setdefault(f"delinquency[{b}].balance", "bucket larger than the pool")
        if num(d.get("count")) and num(rec.get("receivables_count_ending")) and d["count"] > rec["receivables_count_ending"]:
            out.setdefault(f"delinquency[{b}].count", "more delinquent loans than loans")
    # 6. dates in order
    ps, pd_, dd = rec.get("period_start"), rec.get("period_end"), rec.get("distribution_date")
    if ps and pd_ and ps >= pd_:
        out.setdefault("period_end", "period ends before it starts")
    if pd_ and dd and dd <= pd_:
        out.setdefault("distribution_date", "paid before the period ended")
    # 6b. loss identity: gross charge-offs - recoveries = net loss (2% slack for small extra items such as cram-downs)
    g, r, n = rec.get("gross_charge_offs"), rec.get("recoveries"), rec.get("net_losses")
    if all(num(v) for v in (g, r, n)) and abs(g - r - n) > max(1.0, 0.02 * abs(g)):
        for f in ("gross_charge_offs", "recoveries", "net_losses"):
            out.setdefault(f, f"gross {g} - recoveries {r} != net {n}")
    # 6a. a single recoveries line must equal the sum of the subtracted lines listed for it (else two different
    #     loss calculations were mixed)
    comps = [x for x in rec.get("recoveries_components") or [] if num(x)]
    if comps and "recoveries" not in computed and num(r) and abs(abs(r) - abs(sum(comps))) > MONEY_TOL:
        out.setdefault("recoveries", f"recoveries {r} != sum of its components {sum(comps):.2f}")
    # 6c. cumulative loss % = cumulative net losses / initial pool (any of the three can be the wrong one)
    cum, init, pct = rec.get("cumulative_net_losses"), rec.get("initial_pool_balance"), rec.get("cumulative_net_loss_pct")
    if all(num(v) for v in (cum, init, pct)) and init > 0 and abs(100 * cum / init - pct) > 0.02:
        out.setdefault("cumulative_net_loss_pct", f"{pct}% vs {cum}/{init} = {100 * cum / init:.4f}%")
        out.setdefault("cumulative_net_losses", f"{cum}/{init} = {100 * cum / init:.4f}% vs printed {pct}%")
        out.setdefault("initial_pool_balance", f"{cum}/{init} = {100 * cum / init:.4f}% vs printed {pct}%")
    # 6d. once a fifth of the pool has paid down, one month can't hold most of the losses since closing: a period
    #     figure that large was read from a cumulative column
    if all(num(v) for v in (n, cum, init, pe)) and cum > 0 and pe < 0.8 * init and n > 0.5 * cum:
        for f in ("gross_charge_offs", "recoveries", "net_losses"):
            out.setdefault(f, f"this month's net loss {n} is {100 * n / cum:.0f}% of all losses since closing ({cum})")
    # 7. continuity with last month: opening balances = previous closing balances
    if prev:
        # this period's net loss = change in cumulative net losses (catches cumulative-as-period and stale columns)
        c0 = prev.get("cumulative_net_losses")
        if all(num(v) for v in (c0, cum, n)) and abs(cum - c0 - n) > max(1.0, 0.05 * abs(n)):
            out.setdefault("net_losses", f"net {n} != cumulative change {cum - c0:.2f}")
            out.setdefault("cumulative_net_losses", f"change {cum - c0:.2f} != net {n}")
        c0, c1 = prev.get("cumulative_net_loss_pct"), rec.get("cumulative_net_loss_pct")
        # a decrease is always wrong; "unchanged" only when the month's losses were material (percentages are
        # often printed to 2 decimals, so small losses can leave them unchanged)
        nl, pb1 = rec.get("net_losses") or 0, rec.get("pool_balance_beginning")
        material = num(pb1) and pb1 > 0 and nl > 0.0005 * pb1
        if num(c0) and num(c1) and (c1 < c0 or (c1 == c0 and material)):
            out.setdefault("cumulative_net_loss_pct", f"did not rise from last month's {c0} despite net losses")
        if num(init) and num(prev.get("initial_pool_balance")) and abs(init - prev["initial_pool_balance"]) > MONEY_TOL:
            out.setdefault("initial_pool_balance", f"last month's initial pool was {prev['initial_pool_balance']}")
        if num(pb) and num(prev.get("pool_balance_ending")) and abs(pb - prev["pool_balance_ending"]) > MONEY_TOL:
            out.setdefault("pool_balance_beginning", f"last month closed at {prev['pool_balance_ending']}")
        last = {cls(n.get("class")): n for n in prev.get("notes") or [] if isinstance(n, dict)}
        for n in notes:
            c, b = cls(n.get("class")), n.get("beginning_balance")
            pe_ = (last.get(c) or {}).get("ending_balance")
            if num(b) and num(pe_) and abs(b - pe_) > MONEY_TOL:
                out.setdefault(f"notes[{c}].beginning_balance", f"last month closed at {pe_}")
    return out
