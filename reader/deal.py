"""Documents of a deal -> one report: monthly figures, the contract's waterfall checked against them, loan tape stats.

usage: python3 -m reader.deal [FILE ...] [--link URL ...] --backend ollama --model qwen3.5:9b [--out report.json]
Files can be servicer reports, contracts, loan tapes or .zip archives; links can be EDGAR filings, documents or a
trust (its CIK), which downloads the deal's contracts and latest reports.
"""
import argparse
import json
import re
import tempfile

from . import contract, tape
from .checks import issues
from .convert import plain, to_text
from .extract import read_report
from .intake import collect


def iso(date):
    m = re.fullmatch(r"(\d\d)-(\d\d)-(\d{4})", date or "")
    return f"{m[3]}-{m[1]}-{m[2]}" if m else date


def build(docs, backend, model=None, url=None, log=print, progress=None):
    """progress(done, total, step): called before each step; steps are weighted by typical time (a contract ~ 4 reports)."""
    n_rep = sum(d["kind"] == "servicer_report" for d in docs)
    has_contract = any(d["kind"] == "contract" for d in docs)
    total = n_rep + (4 + n_rep if has_contract else 0) + sum(d["kind"] == "loan_tape" for d in docs)
    done = [0]

    def step(name, weight=1):
        log(name)
        if progress:
            progress(done[0], total, name)
        done[0] += weight
    report = {"documents": [{"name": d["name"], "kind": d["kind"]} for d in docs], "months": [], "waterfall": None,
              "tapes": [], "notes": []}
    # 1. servicer reports: checked figures; months of one trust in order, so balances must carry over
    months = []
    for d in [d for d in docs if d["kind"] == "servicer_report"]:
        step(f"reading {d['name']}")
        try:
            months.append(read_report(d["path"], backend, model, url) | {"path": d["path"]})
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
                inp, in_flags = contract.month_inputs(to_text(m["path"]), m["report"], backend, model, url)
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

    unused = [d["name"] for d in docs if d["kind"] == "other"]
    if unused:
        report["notes"].append("not used (not a servicer report, contract or loan tape): " + ", ".join(unused))
    if any(d["kind"] == "prospectus" for d in docs):
        report["notes"].append("the prospectus is not read; the contracts define the payments")
    flagged = sum(len(m["flags"]) for m in report["months"])
    w = report["waterfall"]
    if w:  # a waterfall that couldn't be written, run or checked is itself something to review
        confirmed = w.get("checks") and all(not c.get("error") and all(ln["status"] in ("match", "rounding", "given") for ln in c["lines"])
                                            for c in w["checks"])
        flagged += 1 if w.get("error") or (w.get("problems") and not confirmed) else 0
        flagged += sum(1 if c.get("error") else sum(ln["status"] not in ("match", "rounding", "given") for ln in c["lines"])
                       for c in w.get("checks", []))
    report["flagged"] = flagged
    if progress:
        progress(total, total, "done")
    return report


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
