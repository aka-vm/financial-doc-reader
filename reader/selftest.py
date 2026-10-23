"""No-model self-test on the examples: the converter keeps every answer-key number, and the checks accept every
known-correct answer (a check that fires on a correct report would send good figures to review).

usage: python3 -m reader.selftest
"""
import glob
import json
import os

from .checks import exact, issues, leaves, num, source_numbers
from .convert import to_text

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
    assert exact({"net_losses": 579123}, "net loss 579,123.42")["net_losses"] == 579123.42
    assert exact({"receivables_count_ending": 22010}, "22,009.85")["receivables_count_ending"] == 22010
    print(f"ok: {n} example reports, no lost numbers, no false flags")


if __name__ == "__main__":
    main()
