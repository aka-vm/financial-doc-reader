"""No-model self-test: the converter keeps every answer-key number of the examples, the checks accept every
known-correct answer (a check that fires on a correct report would send good figures to review), documents are
classified, and the waterfall engine pays a toy deal correctly and catches a wrong figure.

usage: python3 -m reader.selftest
"""
import glob
import json
import os

from .backends import gather
from .checks import exact, issues, leaves, num, source_numbers
from .contract import check, close_parens, problems
from .convert import to_text
from .intake import classify

EXAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples")


def main():
    prev, n = {}, 0
    for htm in sorted(glob.glob(os.path.join(EXAMPLES, "*.htm"))):
        key = os.path.basename(htm)[:-4]
        want = json.load(open(htm[:-4] + ".expected.json"))
        text = to_text(htm)
        printed = source_numbers(text)
        lost = [p for p, v in leaves(want) if num(v) and v and round(abs(v), 2) not in printed]
        assert not lost, f"{key}: converter lost {lost}"
        deal = key.split("__")[0]
        flags = issues(want, text, prev.get(deal))
        assert not flags, f"{key}: checks flag a correct answer: {flags}"
        prev[deal] = want
        n += 1
    assert {classify(h) for h in glob.glob(os.path.join(EXAMPLES, "*.htm"))} == {"servicer_report"}
    # waterfall engine and spec validation on a two-class toy deal
    spec = {"definitions": {"int_A": "bal_A * 5 / 100 / 12", "int_B": "bal_B * 6 / 100 / 12", "servicing_fee": "pool_begin * 1 / 100 / 12",
                            "principal": "max(0, bal_A + bal_B - pool_end"},
            "steps": [{"id": "i", "pay": "fee", "kind": "fee", "amount": "servicing_fee"},
                      {"id": "ii", "pay": "interest", "kind": "interest", "amount": "int_A + int_B"},
                      {"id": "iii", "pay": "principal", "kind": "principal", "amount": "principal"},
                      {"id": "iv", "pay": "rest", "kind": "residual", "amount": "0"}],
            "principal_order": [["A"], ["B"]]}
    assert any("not a valid expression" in p for p in problems(spec, ["A", "B"]))
    assert close_parens(spec) == ["principal"] and not problems(spec, ["A", "B"])
    inp = {"bal_A": 600.0, "bal_B": 400.0, "pool_begin": 1200.0, "pool_end": 950.0, "available_funds": 100.0}
    rec = {"notes": [{"class": "A", "interest_paid": 2.5, "principal_paid": 50.0}, {"class": "B", "interest_paid": 2.0, "principal_paid": 0}],
           "servicing_fee": 1.0, "excess_to_residual": 44.5}
    lines = check(spec, inp, rec)["lines"]
    assert all(ln["status"] == "match" for ln in lines), lines
    rec["notes"][0]["principal_paid"] = 49.0  # a wrong report figure must show up as a difference
    assert any(ln["status"] == "differs" for ln in check(spec, inp, rec)["lines"])
    assert gather(['{"a": ', "1", "}"]) == '{"a": 1}'
    try:  # a model looping on whitespace is stopped, not waited out
        gather(['{"a": '] + [" "] * 400)
        raise AssertionError("whitespace runaway not detected")
    except ValueError:
        pass
    assert exact({"net_losses": 579123}, "net loss 579,123.42")["net_losses"] == 579123.42
    assert exact({"receivables_count_ending": 22010}, "22,009.85")["receivables_count_ending"] == 22010
    print(f"ok: {n} example reports, no lost numbers, no false flags; waterfall engine and spec checks pass")


if __name__ == "__main__":
    main()
