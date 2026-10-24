"""Documents of a deal -> one report: monthly figures, the contract's waterfall checked against them, loan tape stats.

usage: python3 -m reader.deal [FILE ...] [--link URL ...] --backend ollama --model qwen3.5:9b [--out report.json]
Files can be servicer reports, contracts, loan tapes or .zip archives; links can be EDGAR filings, documents or a
trust (its CIK), which downloads the deal's contracts and latest reports.
"""
import argparse
import json
import re
import tempfile

from . import contract, general, tape
from .checks import issues
from .convert import plain, to_text
from .extract import read_report
from .intake import collect


def iso(date):
    m = re.fullmatch(r"(\d\d)-(\d\d)-(\d{4})", date or "")
    return f"{m[3]}-{m[1]}-{m[2]}" if m else date


def build(docs, backend, model=None, url=None, log=print, progress=None, extract_model=None, month_model=None):
    """progress(done, total, step): called before each step; steps are weighted by typical time (a contract ~ 4 reports)."""
    n_rep = sum(d["kind"] == "servicer_report" for d in docs)
    has_contract = any(d["kind"] == "contract" for d in docs)
    deal_docs = [d for d in docs if d["kind"] in ("servicer_report", "contract", "loan_tape")]
    others = [] if deal_docs else [d for d in docs if d["kind"] in ("other", "prospectus")][:5]  # not a deal: read what it is
    total = n_rep + (4 + n_rep if has_contract else 0) + sum(d["kind"] == "loan_tape" for d in docs) + 2 * len(others)
    done = [0]

    def step(name, weight=1):
        log(name)
        if progress:
            progress(done[0], total, name)
        done[0] += weight
    report = {"documents": [{"name": d["name"], "kind": d["kind"], "form": d.get("form")} for d in docs], "months": [], "waterfall": None,
              "tapes": [], "read": [], "notes": []}
    # 1. servicer reports: checked figures; months of one trust in order, so balances must carry over
    months = []
    for d in [d for d in docs if d["kind"] == "servicer_report"]:
        step(f"reading {d['name']}")
        try:
            months.append(read_report(d["path"], backend, extract_model or model, url) | {"path": d["path"]})
        except Exception as e:  # one unreadable report shouldn't sink the rest
            report["notes"].append(f"{d['name']}: could not be read ({type(e).__name__}: {e})")
    months.sort(key=lambda m: (m["report"].get("trust") or "", m["report"].get("period_end") or ""))
    last = {}
    for m in months:
        trust = m["report"].get("trust")
        if trust in last:
            m["flags"] = issues(m["report"], to_text(m["path"]), last[trust]) | m["flags"]
            m["verified"] = not m["flags"]
        last[trust] = m["report"]
    report["months"] = [{k: v for k, v in m.items() if k != "path"} for m in months]

    # 2. contracts: the waterfall as a runnable spec, checked against every month we have
    contracts = [d for d in docs if d["kind"] == "contract"]
    if contracts:
        texts = {d["name"]: plain(open(d["path"], encoding="utf-8", errors="replace").read()) for d in contracts}
        classes = [contract.ident(n["class"]) for n in (months[-1]["report"].get("notes") or [])] if months else []
        if not classes:
            report["notes"].append("no servicer report given, so the note classes come from the contract alone")
        step("reading the contracts for the priority of payments (the longest step: a few minutes)", 4)
        try:
            w = contract.write_spec(texts, classes, backend, model, url, log)
        except Exception as e:
            w = {"error": f"{type(e).__name__}: {e}"}
        w["checks"] = []
        for m in months if "spec" in w else []:
            step(f"running the waterfall on {m['file']}")
            try:
                inp, in_flags = contract.month_inputs(to_text(m["path"]), m["report"], backend, month_model or model, url)
                res = contract.check(w["spec"], inp, m["report"], m["flags"], in_flags)
                res |= {"inputs": {k: inp[k] for k in contract.MONTH_FIELDS}, "input_flags": in_flags}
            except Exception as e:  # this month can't be checked; say so and go on
                res = {"error": f"{type(e).__name__}: {e}", "lines": [], "inputs": {}, "input_flags": {}}
            w["checks"].append({"file": m["file"], "period_end": m["report"].get("period_end")} | res)
        if "spec" in w and not months:
            report["notes"].append("waterfall not verified: add a servicer report of the same deal to check it")
        report["waterfall"] = w

    # 3. loan tapes: pool statistics, and the tape's balance against the same month's report
    for d in [d for d in docs if d["kind"] == "loan_tape"]:
        step(f"summarising loan tape {d['name']}")
        t = tape.summary(d["path"]) | {"file": d["name"]}
        same = [m for m in months if m["report"].get("period_end") == iso(t.get("period_end"))]
        if same:
            t["check"] = tape.against_report(t, same[0]["report"])
        report["tapes"].append(t)

    # 4. no deal documents at all: say what each document is and what it states, with checked quotes
    for d in others:
        step(f"reading {d['name']}", 2)
        try:
            report["read"].append(general.read_document(d["path"], backend, model, url, d.get("form")) | {"file": d["name"]})
        except Exception as e:
            report["notes"].append(f"{d['name']}: could not be read ({type(e).__name__}: {e})")

    unused = [d["name"] for d in docs if d["kind"] == "other" and d not in others]
    if unused:
        report["notes"].append("not used (not a servicer report, contract or loan tape): " + ", ".join(unused))
    if any(d["kind"] == "prospectus" for d in docs) and not others:
        report["notes"].append("the prospectus is not read; the contracts define the payments")
    flagged = sum(len(m["flags"]) for m in report["months"])
    w = report["waterfall"]
    if w:  # a waterfall that couldn't be written, run or checked is itself something to review
        confirmed = w.get("checks") and all(not c.get("error") and all(ln["status"] in ("match", "rounding", "given") for ln in c["lines"])
                                            for c in w["checks"])
        flagged += 1 if w.get("error") or (w.get("problems") and not confirmed) else 0
        flagged += sum(1 if c.get("error") else sum(ln["status"] not in ("match", "rounding", "given") for ln in c["lines"])
                       for c in w.get("checks", []))
    flagged += sum(1 for g in report["read"] for f in g.get("facts", []) if f.get("problem"))
    report["flagged"] = flagged
    if progress:
        progress(total, total, "done")
    return report


def money(v, pct=False):
    if v is None:
        return "—"
    if pct:
        return f"{v}%"
    return f"{v:,.2f}" if isinstance(v, float) and v != int(v) else f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def review_items(r):
    """Everything a person should look at, as (item, value, why)."""
    out = []
    for m in r["months"]:
        for k, why in m["flags"].items():
            out.append((f"{m['report'].get('period_end') or m['file']}: {k.replace('_', ' ')}", "", why))
    w = r.get("waterfall")
    if w:
        checks = [c for c in w.get("checks", []) if not c.get("error")]
        confirmed = checks and all(ln["status"] in ("match", "rounding", "given") for c in checks for ln in c["lines"])
        if w.get("error"):
            out.append(("payment waterfall", "", w["error"]))
        elif w.get("problems") and not confirmed:
            out.append(("payment waterfall", "", "the contract could not be fully turned into payment rules"))
        for c in w.get("checks", []):
            if c.get("error"):
                out.append((f"payment waterfall, {c.get('period_end')}", "", c["error"]))
            for ln in c.get("lines", []):
                if ln["status"] in ("differs", "unknown"):
                    out.append((f"payment waterfall, {c.get('period_end')}: {ln['line']}", money(ln["report"]),
                                f"the contract's rules give {money(ln['contract'])}" if ln["status"] == "differs" else ln["note"]))
    for g in r.get("read", []):
        for f in g.get("facts", []):
            if f.get("problem"):
                out.append((f"{g['file']}: {f['label']}", f["value"], f["problem"]))
    for t in r["tapes"]:
        if t.get("error"):
            out.append((f"loan tape {t['file']}", "", t["error"]))
        elif (t.get("check") or {}).get("status") == "differs":
            out.append((f"loan tape {t['file']}", money(t["balance"]), f"differs from the report's pool balance by {money(t['check']['difference'])}"))
    return out


def to_markdown(r, footer=""):
    """The deal report as Markdown (same content as the page)."""
    items, md = review_items(r), []
    last = r["months"][-1]["report"] if r["months"] else {}
    md.append(f"# {last.get('trust') or ('Document report' if r.get('read') else 'Deal report')}")
    if r.get("read") and not r["months"] and not r.get("waterfall") and not r["tapes"]:
        for g in r["read"]:
            md.append(f"\n## {g.get('filer')}: {g.get('document_type')} ({g['file']}"
                      + (f", EDGAR form {g['form']}" if g.get("form") else "") + (f", {g['date']}" if g.get("date") else "") + ")\n")
            if g["read_words"] < g["words"]:
                md.append(f"_Read the first {g['read_words']:,} of {g['words']:,} words._\n")
            md.append(f"**Summary** (the model's words): {g.get('summary')}\n\n| Fact | Value | Checked |\n|---|---|---|")
            for f in g.get("facts", []):
                md.append(f"| {f['label']} | {f['value']} | {'yes: quoted in the document' if not f.get('problem') else 'NO: ' + f['problem']} |")
        items = review_items(r)
        md.append("\n## Needs review\n")
        md.append("\n".join(f"- **{a}** ({v}): {why}" for a, v, why in items) or "Nothing: every fact is quoted from the document.")
        return "\n".join(md) + (f"\n\n---\n{footer}" if footer else "")
    if not r["months"] and not r.get("waterfall") and not r["tapes"]:
        what = ", ".join(d["name"] + (f" (EDGAR form {d['form']})" if d.get("form") else "") for d in r["documents"])
        return (md[0] + f"\n\n**Nothing to report.** This reads US auto-loan asset-backed deals: monthly servicer reports, "
                f"the deal contracts and loan tapes. None of these documents is one of those: {what}. For a deal, give a "
                "trust's name (e.g. \"CarMax Auto Owner Trust 2024-1\"), its CIK, or a link to one of its 10-D filings."
                + (f"\n\n---\n{footer}" if footer else ""))
    md.append(f"**{'Verified: every figure passed the checks.' if not items else f'{len(items)} item(s) need review (listed at the end).'}** "
              f"Built from {len(r['documents'])} documents.")
    if last:
        notes_out = sum(n.get("ending_balance") or 0 for n in last.get("notes") or [])
        dq60 = sum(d.get("balance") or 0 for d in last.get("delinquency") or [] if int((re.findall(r"\d+", str(d.get("bucket"))) or [0])[0]) >= 60)
        pool, init = last.get("pool_balance_ending"), last.get("initial_pool_balance")
        md.append(f"\n## Deal at a glance (period ending {last.get('period_end')}, paid {last.get('distribution_date')})\n")
        md.append("| | |\n|---|---|")
        for k, v in [("Pool balance", money(pool)), ("Pool factor", money(round(100 * pool / init, 2) if pool and init else None, True)),
                     ("Notes outstanding", money(notes_out)), ("Overcollateralization", money(last.get("overcollateralization_ending"))),
                     ("Reserve account", money(last.get("reserve_account_ending"))), ("Net losses this month", money(last.get("net_losses"))),
                     ("Cumulative net loss (% of initial pool)", money(last.get("cumulative_net_loss_pct"), True)),
                     ("Delinquent 60+ days (% of pool)", money(round(100 * dq60 / pool, 2) if pool else None, True)),
                     ("Paid to the residual holder", money(last.get("excess_to_residual")))]:
            md.append(f"| {k} | {v} |")
        md.append("\n## Notes\n\n| Class | Balance before | Interest paid | Principal paid | Balance after |\n|---|---|---|---|---|")
        for n in last.get("notes") or []:
            if any(n.get(f) for f in ("beginning_balance", "ending_balance", "interest_paid", "principal_paid")):
                md.append(f"| {n.get('class')} | {money(n.get('beginning_balance'))} | {money(n.get('interest_paid'))} | "
                          f"{money(n.get('principal_paid'))} | {money(n.get('ending_balance'))} |")
    w = r.get("waterfall")
    if w and w.get("spec"):
        c = ([c for c in w["checks"] if not c.get("error")] or [None])[-1]
        ok = c and all(ln["status"] in ("match", "rounding", "given") for ln in c["lines"])
        md.append(f"\n## Payment waterfall (from {w['document']}, Section {w['section']})\n")
        md.append("All payments agree with the servicer report." if ok else
                  "Payment order only: the amounts could not be confirmed against a servicer report.")
        md.append("\n| Order | Paid to / for | Amount |\n|---|---|---|")
        for s in (c["steps"] if ok else w["spec"].get("steps", [])):
            md.append(f"| {s.get('id')} | {s.get('pay')} | {money(s.get('paid')) if ok else '—'} |")
    for t in r["tapes"]:
        if not t.get("error"):
            md.append(f"\n## Loan pool (tape, {t.get('period_end')})\n")
            count_note = f" ({money(t['total_assets'])} total tape rows)" if t.get("total_assets") is not None else ""
            md.append(f"{money(t['loans'])} active loans with positive ending balance{count_note}; "
                      f"balance {money(t['balance'])}, weighted average rate {t['wa_rate_pct']}%, "
                      f"credit score {t['wa_credit_score']}, remaining term {t['wa_remaining_term']} months."
                      + (f" Tape vs report pool balance: {t['check']['status']} "
                         + ("within the comparison tolerance " if t['check']['status'] in ("match", "close") else "beyond the comparison tolerance ")
                         + f"(difference {money(t['check']['difference'])})." if t.get("check") else ""))
            if t.get("missing_delinquency_assets"):
                md.append(f"Delinquency status is unknown for {money(t['missing_delinquency_assets'])} active loans "
                          f"with balance {money(t['missing_delinquency_balance'])}. They remain in the pool balance "
                          "and are not classified as current or delinquent.")
            if t.get("delinquency_balance"):
                md.append("\n| Loan-tape delinquency status | Balance |\n|---|---|")
                for bucket, balance in t["delinquency_balance"].items():
                    label = "Unknown / not reported" if bucket == "unknown" else "Current / under 30 days" if bucket == "current" else bucket + " days"
                    md.append(f"| {label} | {money(balance)} |")
    md.append("\n## Needs review\n")
    md.append("\n".join(f"- **{a}**{f' ({v})' if v else ''}: {why}" for a, v, why in items) or "Nothing: every figure passed the checks.")
    if r["notes"]:
        md.append("\n" + "\n".join(f"_{x}_" for x in r["notes"]))
    return "\n".join(md) + (f"\n\n---\n{footer}" if footer else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--link", action="append", default=[])
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--model")
    ap.add_argument("--url")
    ap.add_argument("--out")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        res = build(collect(a.files, a.link, folder), a.backend, a.model, a.url)
    text = json.dumps(res, indent=1)
    open(a.out, "w").write(text) if a.out else print(text)
    print(f"# {len(res['months'])} monthly reports, waterfall {'yes' if res['waterfall'] else 'no'}, "
          f"{len(res['tapes'])} tapes, {res['flagged']} items flagged for review")


if __name__ == "__main__":
    main()
