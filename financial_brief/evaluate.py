"""Reproducible live-model evaluation. Test split first; validation is scored unchanged.

python -m financial_brief.evaluate --split test --out /tmp/ledger-eval
"""
import argparse
import copy
import json
import os
import re
import tempfile
import time
from pathlib import Path

from .engine import answer, build, numbers, squash, valid_claim

ROOT = Path(__file__).resolve().parent.parent
CASES = Path(__file__).parent / 'eval' / 'cases.json'


def run(case, output, model, url, replay=None):
    started = time.monotonic()
    result = {'id': case['id'], 'split': case['split'], 'type': case['type']}
    required = list(case['required'])
    if 'path' in case:
        golden = json.loads((ROOT / case['path']).with_suffix('.expected.json').read_text())
        required = [f"{golden[key]:,.2f}" for key in
                    ('pool_balance_beginning', 'pool_balance_ending', 'servicing_fee', 'net_losses')]
    raw = []
    from reader.backends import call
    recorded = iter(json.loads((replay / f"{case['id']}.raw.json").read_text())) if replay else None

    def ask(*args, **kwargs):
        got = copy.deepcopy(next(recorded)) if recorded is not None else call(*args, **kwargs)
        raw.append(copy.deepcopy(got))
        return got

    try:
        with tempfile.TemporaryDirectory() as folder:
            if 'path' in case:
                path = ROOT / case['path']
            else:
                path = Path(folder) / (case['id'] + '.txt')
                path.write_text(case['text'])
            report = build([path], model, url, lambda *p: print(case['id'], *p, flush=True), ask=ask)
        response = answer(case['question'], report, model, url, ask=ask)
        fact_text = squash(' '.join(f['value'] for f in report['facts']))
        found = [v for v in required if squash(v) in fact_text]
        missing = [v for v in required if v not in found]
        claims = [c for key in ('overview', 'highlights', 'risks') for c in report[key]]
        source_checks = all(valid_claim(c, report['facts']) for c in claims)
        forbidden = case.get('forbidden', '')
        prose = squash(' '.join(c['text'] for c in claims))
        qa_pass = (bool(re.search(case['answer_regex'], response['answer'])) if case.get('answer_regex')
                   else case['answer_contains'].casefold() in response['answer'].casefold())
        result.update(status='completed', facts=len(report['facts']), withheld=report['rejected'],
                      expected_values=len(required), matched_values=len(found), missing_values=missing,
                      claim_checks=source_checks, injection_pass=not forbidden or forbidden not in prose,
                      qa_pass=qa_pass, answer=response, warnings=report['warnings'])
        result['context_claims_withheld'] = report.get('context_review', {}).get('claims_withheld', 0)
        (output / f"{case['id']}.report.json").write_text(json.dumps(report, indent=2))
    except Exception as exc:
        result.update(status='error', error=f'{type(exc).__name__}: {exc}')
    result['seconds'] = round(time.monotonic() - started, 1)
    result['mode'] = 'recorded-response replay' if replay else 'live API'
    (output / f"{case['id']}.raw.json").write_text(json.dumps(raw, indent=2))
    (output / f"{case['id']}.result.json").write_text(json.dumps(result, indent=2))
    print('RESULT', json.dumps({k:v for k,v in result.items() if k != 'answer'}), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['test', 'validation', 'all'], default='test')
    parser.add_argument('--out', type=Path, default=Path('/tmp/ledger-eval'))
    parser.add_argument('--model', default=os.getenv('BRIEF_MODEL', 'qwen3.8'))
    parser.add_argument('--url', default=os.getenv('BRIEF_MODEL_URL', 'http://localhost:8001/v1'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--replay-from', type=Path, help='Recheck recorded responses without another model call')
    parser.add_argument('--retry-failed-answers', action='store_true', help='Retry only failed Q&A using saved reports')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    for case in json.loads(CASES.read_text()):
        if args.split != 'all' and case['split'] != args.split:
            continue
        existing = args.out / f"{case['id']}.result.json"
        if args.retry_failed_answers and existing.exists():
            result = json.loads(existing.read_text())
            if result.get('status') == 'completed' and not result.get('qa_pass'):
                from reader.backends import call
                report = json.loads((args.out / f"{case['id']}.report.json").read_text())
                replies = []
                def ask(*a, **kw):
                    reply = call(*a, **kw)
                    replies.append(copy.deepcopy(reply))
                    return reply
                start = time.monotonic()
                response = answer(case['question'], report, args.model, args.url, ask=ask)
                passed = (bool(re.search(case['answer_regex'], response['answer'])) if case.get('answer_regex')
                          else case['answer_contains'].casefold() in response['answer'].casefold())
                result.update(answer=response, qa_pass=passed, qa_retry_seconds=round(time.monotonic()-start, 1), qa_retried=True)
                existing.write_text(json.dumps(result, indent=2))
                (args.out / f"{case['id']}.answer-retry.raw.json").write_text(json.dumps(replies, indent=2))
                print('ANSWER RETRY',case['id'],passed,flush=True)
            results.append(result)
        elif args.resume and existing.exists():
            results.append(json.loads(existing.read_text()))
        else:
            results.append(run(case, args.out, args.model, args.url, args.replay_from))
        (args.out / f'{args.split}-summary.json').write_text(json.dumps(results, indent=2))
    print('COMPLETED', len(results), 'cases', flush=True)


if __name__ == '__main__':
    main()
