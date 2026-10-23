"""Servicer report -> standard figures, each either passing every check or flagged with the reason.

usage: python3 -m reader.extract REPORT [REPORT ...] --backend ollama --model qwen3.5:9b [--url URL] [--out DIR]
Reports of the same trust given in month order are also checked against each other (balances carry over).
"""
import argparse
import json
import os

from .backends import call
from .checks import exact, finalize, issues
from .convert import to_text

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPT = open(os.path.join(HERE, "prompt.md")).read()
SCHEMA = json.load(open(os.path.join(HERE, "schema.json")))


def read_report(path, backend, model=None, url=None, prev=None):
    text = to_text(path)
    prompt = f"{PROMPT}\n\nJSON schema:\n{json.dumps(SCHEMA)}\n\nReport:\n{text}"
    data = finalize(exact(call(backend, model, prompt, SCHEMA, url), text))
    flags = issues(data, text, prev)
    for f in data.get("ambiguous_fields") or []:
        flags.setdefault(f, "the report prints more than one value for this")
    return {"file": os.path.basename(path), "report": data, "flags": flags, "verified": not flags}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--backend", default="ollama",
                    choices=["ollama", "link", "codex", "claude-code", "gemini-cli", "anthropic", "openai", "gemini"])
    ap.add_argument("--model")
    ap.add_argument("--url", help="base URL for --backend link, e.g. http://my-server:8000/v1")
    ap.add_argument("--out", help="write one JSON per report here (default: print)")
    a = ap.parse_args()
    last = {}
    for path in a.reports:
        res = read_report(path, a.backend, a.model, a.url)
        trust = res["report"].get("trust")
        if trust in last:  # same trust, next month: re-check with continuity
            res["flags"] = issues(res["report"], to_text(path), last[trust]) | res["flags"]
            res["verified"] = not res["flags"]
        last[trust] = res["report"]
        if a.out:
            os.makedirs(a.out, exist_ok=True)
            json.dump(res, open(os.path.join(a.out, os.path.splitext(res["file"])[0] + ".json"), "w"), indent=1)
        else:
            print(json.dumps(res, indent=1))
        status = "all figures pass the checks" if res["verified"] else f"{len(res['flags'])} flagged for review"
        print(f"# {res['file']}: {status}", flush=True)


if __name__ == "__main__":
    main()
