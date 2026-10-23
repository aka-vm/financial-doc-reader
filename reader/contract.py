"""Deal contract -> the priority of payments as a spec the code can run, checked against a servicer report.

1. find the payments section (the clause list "first, ... second, ..." that applies the month's available funds)
2. build a context pack: that section, the sections it cites (in any of the deal's documents), and every defined
   term it relies on, followed through the definitions
3. the model writes the spec (formulas in a tiny safe language); code rejects any formula that doesn't parse or uses
   an unknown name, and sends the problems back for a fix
4. the engine runs the spec on a month's opening figures; each class's interest and principal, the servicing fee and
   the residual are compared with what the servicer report says was paid. A line that doesn't match is flagged.
"""
import ast
import json
import operator
import os
import re

from .backends import call
from .convert import plain

DEF_START = re.compile(r"“\s*([A-Z][^”]{1,90}?)\s*”\s*(?:shall\s+)?(?:means?|has the meaning|shall have the meaning|refers)")
# "Section 2.8 Payments", "SECTION 2.8", or a bare "3.8 Servicing Compensation ." (the title must start with a letter,
# so "1.00% of the Pool Balance" is never a heading)
SECTION = re.compile(r"^(?:(?:SECTION|Section)\s+)?(\d{1,2}\.\d{1,2})\.?(?:\s+([A-Z][^\n]{2,120}))?$")


def sections(text):
    """Number -> {title, text}. A number can appear twice (table of contents, then the body): keep the longest."""
    found, cur = [], None
    for line in text.split("\n"):
        m = SECTION.match(line.strip())
        # a heading line is short; long lines starting "Section 2.3(b), ..." are cross-references
        if m and len(line) < 160 and not re.match(r"^\(", m.group(2) or ""):
            cur = {"num": m.group(1), "title": (m.group(2) or "").strip(), "text": []}
            found.append(cur)
            continue
        if cur:
            if not cur["title"] and line.strip():
                cur["title"] = line.strip()[:120]  # title printed on the line after "Section 2.8"
            cur["text"].append(line)
    out = {}
    for s in found:
        text = "\n".join(s["text"])
        if len(text) > len(out.get(s["num"], {}).get("text", "")):
            out[s["num"]] = {"title": s["title"], "text": text}
    return out


def definitions(text):
    flat = re.sub(r"\s+", " ", text)
    starts = [(m.start(), m.group(1).strip()) for m in DEF_START.finditer(flat)]
    out = {}
    for (pos, term), nxt in zip(starts, starts[1:] + [(len(flat), None)]):
        body = flat[pos:min(nxt[0], pos + 6000)].strip()
        if term not in out or len(body) > len(out[term]):  # keep the fullest definition of a term
            out[term] = body
    return out


def used_terms(text, defs):
    return {t for t in defs if len(t) > 3 and re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text)}


def context_pack(section_text, defs, max_terms=60, extra_texts=()):
    """Defined terms needed to read a section, breadth-first: terms the section uses, then terms the extra (cross-
    referenced) texts use, then what those definitions rely on, level by level, up to max_terms."""
    seen, level = [], []
    for text in (section_text, *extra_texts):
        level += [t for t in sorted(used_terms(text, defs), key=len, reverse=True) if t not in level]
    while level and len(seen) < max_terms:
        nxt = []
        for t in level:
            if t in seen or len(seen) >= max_terms:
                continue
            seen.append(t)
            nxt += [u for u in sorted(used_terms(defs[t], defs), key=len, reverse=True) if u not in seen and u not in nxt]
        level = nxt
    return seen


XREF = re.compile(r"Section\s+(\d+\.\d+)(?:\([a-z0-9]+\))*(?:\s+of\s+the\s+((?:(?:[A-Z][a-z]+|and|of)\s+)*?(?:Agreement|Indenture)))?")


def doc_names(texts):
    """Each document's own title, taken from its cover page: the ALL-CAPS '... AGREEMENT' / 'INDENTURE' printed just
    before 'Dated as of' (an opening page also mentions other agreements, so first-mention is not enough)."""
    names = {}
    for path, t in texts.items():
        head = re.sub(r"\s+", " ", t[:6000])
        m = re.search(r"((?:[A-Z][A-Z&,\-]+ ){0,5}(?:AGREEMENT|INDENTURE))\s*,?\s*(?:dated|DATED|Dated)", head)
        if m:
            title = re.sub(r"^(?:THIS |THE )?(?:SECOND )?(?:AMENDED AND RESTATED )?", "", m.group(1)).title()
            names[title.replace(" And ", " and ")] = path
    return names


def build_pack(section, doc, texts, max_terms=170, max_xrefs=12):
    """Section text + sections it cross-references (in any document) + every defined term used, transitively."""
    secs = {d: sections(t) for d, t in texts.items()}
    defs = {}
    for t in texts.values():
        defs.update(definitions(t))
    names = doc_names(texts)
    main = secs[doc][section]
    parts, seen = [f"[{doc} Section {section} - {main['title']}]\n{main['text']}"], {(doc, section)}
    for m in XREF.finditer(main["text"]):
        target = names.get(re.sub(r"\s+", " ", m.group(2)).strip(), None) if m.group(2) else doc
        if target is None:
            continue  # cross-reference to a document we don't have
        key = (target, m.group(1))
        if key in seen or m.group(1) not in secs.get(target, {}) or len(seen) > max_xrefs:
            continue
        seen.add(key)
        x = secs[target][m.group(1)]
        parts.append(f"[{target} Section {m.group(1)} - {x['title']}]\n{x['text'][:6000]}")
    body = "\n\n".join(parts)
    # the payments section's own terms (and what they rely on) come first; cross-referenced sections only fill
    # what room is left, so the cap can never push out a definition the waterfall itself needs
    terms = context_pack(main["text"], defs, max_terms, extra_texts=parts[1:])
    return body + "\n\nDEFINITIONS USED\n" + "\n\n".join(defs[t] for t in terms), sorted(k for k in seen if k != (doc, section))


# ---- waterfall engine: definitions in dependency order, then clauses paid in order ----
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.USub: operator.neg}
FUNCS = {"min": min, "max": max, "sum": sum, "round": round}  # servicers round components to the cent: round(x, 2)


def evaluate(expr, env):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise KeyError(f"unknown name {n.id!r} in {expr!r}")
            return env[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in OPS:
            return OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
            return FUNCS[n.func.id](*[ev(a) for a in n.args])
        if isinstance(n, (ast.List, ast.Tuple)):
            return [ev(e) for e in n.elts]
        raise ValueError(f"not allowed in a waterfall expression: {ast.dump(n)[:60]}")
    return ev(ast.parse(expr, mode="eval"))


def run(spec, inputs):
    env = dict(inputs)
    # evaluate definitions in dependency order (JSON key order carries no meaning; some tools sort keys)
    pending = {k: v for k, v in spec.get("definitions", {}).items() if k not in inputs}
    while pending:
        done = []
        for name, expr in pending.items():
            try:
                env[name] = evaluate(expr, env)
                done.append(name)
            except KeyError:
                continue
        if not done:
            evaluate(next(iter(pending.values())), env)  # nothing resolvable: re-raise the unknown-name error
        for name in done:
            pending.pop(name)
    cash = env["available_funds"]
    paid, principal_pool = [], 0.0
    for s in spec["steps"]:
        due = cash if s["kind"] == "residual" else max(0.0, evaluate(s["amount"], env))
        amt = round(min(due, cash), 2)
        cash = round(cash - amt, 2)
        paid.append({"id": s["id"], "pay": s["pay"], "kind": s["kind"], "due": round(due, 2), "paid": amt,
                     "shortfall": round(due - amt, 2)})
        if s["kind"] == "principal":
            principal_pool += amt
    # principal to classes: sequential groups, pro rata within a group
    by_class, left = {}, round(principal_pool, 2)
    for group in spec["principal_order"]:
        bal = {c: env.get(f"bal_{c.replace('-', '')}", 0.0) for c in group}
        need = sum(bal.values())
        take = min(left, need)
        for c in group:
            by_class[c] = round(take * bal[c] / need, 2) if need else 0.0
        left = round(left - take, 2)
    return {"steps": paid, "principal_by_class": by_class, "definitions": {k: round(env[k], 2) for k in spec.get("definitions", {})}}


# ---- from contract documents to a checked waterfall ----
HERE = os.path.dirname(os.path.abspath(__file__))
TASK = open(os.path.join(HERE, "spec_task.md")).read()
SPEC_SCHEMA = json.load(open(os.path.join(HERE, "spec_schema.json")))
INPUT_NAMES = {"pool_begin", "pool_end", "pool_cutoff", "available_funds", "unreimbursed_advances", "capped_expenses",
               "uncapped_expenses", "reserve_deficiency", "reserve_balance"}
ORD = re.compile(r"\((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\)|\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s*,", re.I)
MONTH_FIELDS = {
    "available_funds": "total cash available for the waterfall on this distribution date (Available Funds / Available Amount)",
    "reserve_balance": "reserve account balance before this date's deposits and withdrawals",
    "capped_expenses": "each trustee, owner trustee or asset representations reviewer fee paid in the waterfall this date",
    "uncapped_expenses": "each other expense paid in the waterfall this date (not the servicing fee)",
    "unreimbursed_advances": "servicer advances reimbursed from available funds this date",
    "reserve_deficiency": "amount deposited to bring the reserve account up to its required level this date",
}
LISTS = {"capped_expenses", "uncapped_expenses"}  # listed line by line as printed; code adds them up
MONTH_SCHEMA = {"type": "object", "additionalProperties": False, "required": list(MONTH_FIELDS),
                "properties": {k: {"type": "array", "items": {"type": "number"}} if k in LISTS else {"type": ["number", "null"]}
                               for k in MONTH_FIELDS}}


def ident(cls):
    """'Class A-2a Notes' -> 'A2a' (the spec's identifier-safe class id)."""
    return re.sub(r"(?i)\bclass\b|\bnotes?\b|[\s\-]", "", str(cls))


def find_payments(texts):
    """(document, section number, title) of the priority of payments: the section with the most ordinal clauses,
    weighted up when it applies available funds and its title reads like payments / distributions."""
    best = (0, None, None, "")
    for doc, t in texts.items():
        for num, s in sections(t).items():
            body = s["text"][:20000]
            score = len(ORD.findall(body))
            score *= 2 if re.search(r"(?i)available funds|amounts? on deposit in the collection account", body) else 1
            score *= 2 if re.search(r"(?i)payment|distribut|priorit|application", s["title"]) else 1
            best = max(best, (score, doc, num, s["title"]), key=lambda b: b[0])
    return best[1:]


def names_in(expr):
    return {n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)} - set(FUNCS)


def problems(spec, classes):
    out, known = [], INPUT_NAMES | {f"bal_{c}" for c in classes} | set(spec.get("definitions", {}))
    exprs = [("definition", k, e) for k, e in spec.get("definitions", {}).items()]
    exprs += [("step", s.get("id"), s.get("amount", "0")) for s in spec.get("steps", [])]
    for where, k, e in exprs:
        try:
            unknown = names_in(e) - known
        except SyntaxError as x:
            out.append(f"{where} {k!r} is not a valid expression ({x.msg}): {e}")
            continue
        out += [f"{where} {k!r} uses {n!r}, which is neither an input nor a definition: use an input (fees and expenses "
                f"of trustees, reviewers and others are capped_expenses / uncapped_expenses) or add {n!r} to definitions"
                for n in sorted(unknown)]
    defs = spec.get("definitions", {})

    def loops(name, path=()):
        try:
            return name in path or any(loops(d, path + (name,)) for d in names_in(defs[name]) if d in defs)
        except SyntaxError:
            return False
    out += [f"definition {k!r} refers to itself: write it from the contract's terms and the inputs" for k in defs if loops(k)]
    for group in spec.get("principal_order", []):
        out += [f"principal_order names class {c!r}; the note classes are {classes}" for c in group if c not in classes]
    return out


def close_parens(spec):
    """Long formulas sometimes end one ')' short; add the missing closers when that alone makes them parse.
    The comparison with the servicer report still has to confirm the result."""
    fixed = []
    slots = [(spec.get("definitions", {}), k) for k in spec.get("definitions", {})] + [(s, "amount") for s in spec.get("steps", [])]
    for holder, k in slots:
        e = holder[k]
        gap = e.count("(") - e.count(")")
        if gap > 0:
            try:
                ast.parse(e + ")" * gap, mode="eval")
                holder[k] = e + ")" * gap
                fixed.append(k if holder is spec.get("definitions") else f"clause {holder.get('id')}")
            except SyntaxError:
                pass
    return fixed


def write_spec(texts, classes, backend, model=None, url=None, log=print, rounds=2):
    doc, num, title = find_payments(texts)
    if not doc:
        return {"error": "no priority-of-payments section found in the contracts"}
    log(f"payments section: {doc} Section {num} ({title.strip()[:60]})")
    pack, xrefs = build_pack(num, doc, texts)
    log(f"context pack: {len(pack.split())} words, {len(xrefs)} cross-referenced sections")
    ask = f"{TASK}\n- The note classes of this deal are: {', '.join(classes)}.\n\nContract excerpt:\n{pack}"
    spec = call(backend, model, ask, SPEC_SCHEMA, url, max_tokens=16384)
    for r in range(rounds):
        issues = problems(spec, classes)
        if not issues:
            break
        log(f"spec has {len(issues)} problem(s); asking for a fix (round {r + 1})")
        try:
            spec = call(backend, model, f"{ask}\n\nYour previous answer:\n{json.dumps(spec)}\n\nIt has these problems:\n- "
                        + "\n- ".join(issues) + "\nReturn the full corrected JSON.", SPEC_SCHEMA, url, max_tokens=16384)
        except RuntimeError as e:  # keep the last spec; its problems are reported
            log(f"the fix failed ({e}); keeping the previous spec")
            break
    closed = close_parens(spec)
    return {"document": doc, "section": num, "title": title.strip(), "spec": spec,
            "problems": problems(spec, classes), "auto_closed": closed}


def month_inputs(report_text, rec, backend, model=None, url=None):
    """The waterfall's opening figures for one month: balances from the checked servicer record, the rest read by the
    model from the report (each must be printed in the report)."""
    from .checks import source_numbers
    asks = "\n".join(f"- {k}: {v}" for k, v in MONTH_FIELDS.items())
    got = call(backend, model, "From this monthly servicer report, give these figures for this distribution date, as "
               "printed, written as plain JSON numbers without $ or thousands commas (29,108,512.47 -> 29108512.47); "
               f"null if the report doesn't print one:\n{asks}\n\nReport:\n{report_text}", MONTH_SCHEMA, url, max_tokens=4096)
    nums, flags = source_numbers(report_text), {}
    inp = {k: 0.0 for k in INPUT_NAMES}
    for k, v in got.items():
        parts = [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, (int, float))]
        missing = [x for x in parts if x and round(abs(x), 2) not in nums]
        if missing:
            flags[k] = f"{', '.join(map(str, missing))} not printed in the report"
        inp[k] = round(sum(abs(float(x)) for x in parts), 2)
    paid_out = sum((n.get("interest_paid") or 0) + (n.get("principal_paid") or 0) for n in rec.get("notes") or [])
    paid_out += rec.get("servicing_fee") or 0
    if inp["available_funds"] < 0.999 * paid_out:  # cash paid out this month can't exceed the cash available
        flags["available_funds"] = f"{inp['available_funds']:,.2f} is less than the {paid_out:,.2f} paid to notes and servicer"
    inp.update(pool_begin=rec.get("pool_balance_beginning") or 0.0, pool_end=rec.get("pool_balance_ending") or 0.0,
               pool_cutoff=rec.get("initial_pool_balance") or 0.0)
    inp.update({f"bal_{ident(n['class'])}": n.get("beginning_balance") or 0.0 for n in rec.get("notes") or []})
    return inp, flags


def check(spec, inp, rec, rec_flags=None, input_flags=None):
    """Lines the contract determines vs what the servicer report says was paid. Each line: match / differs / unknown."""
    rec_flags = rec_flags or {}
    defs0 = spec.get("definitions", {})

    def loops(name, path=()):
        return name in path or any(loops(d, path + (name,)) for d in names_in(defs0[name]) if d in defs0)
    # a definition that refers to itself defines nothing: treat its name as unknown (e.g. "sofr": "sofr")
    spec = dict(spec, definitions={k: v for k, v in defs0.items() if not loops(k)})
    if input_flags:  # a doubtful opening figure means no line can be confirmed
        return {"error": "the month's opening figures are doubtful: " + "; ".join(f"{k}: {v}" for k, v in input_flags.items()),
                "lines": []}
    env = dict(inp)
    known = set(env) | set(spec.get("definitions", {}))
    deps = {k: names_in(e) for k, e in spec.get("definitions", {}).items()}
    missing = set().union(*[v - known for v in deps.values()], set())
    for s in spec.get("steps", []):
        missing |= names_in(s.get("amount", "0")) - known

    def tainted(name, seen=()):
        return name not in given and (name in missing or any(tainted(d, seen + (name,)) for d in deps.get(name, ()) if d not in seen))
    # a class whose rate depends on something the contract doesn't fix (a floating benchmark) can't be computed:
    # use the interest the report printed for it, so every other line can still be checked
    given = {}
    for n in rec.get("notes") or []:
        name = f"int_{ident(n['class'])}"
        if (name in missing or name in deps and tainted(name)) and isinstance(n.get("interest_paid"), (int, float)):
            given[name] = env[name] = float(n["interest_paid"])
    env.update({m: 0.0 for m in missing})  # still runs; every line that depends on these is marked unknown
    flow_unknown = any(tainted(n) for s in spec.get("steps", []) for n in names_in(s.get("amount", "0")))
    try:
        res = run(spec, env)
    except Exception as e:  # a spec that can't run is reported, not guessed around
        return {"error": f"spec does not run: {type(e).__name__}: {e}", "lines": []}
    lines = []

    def add(label, contract, report, unknown, report_flag=None):
        if unknown:
            status, note = "unknown", f"uses {', '.join(sorted(missing))}, which the contract excerpt doesn't define"
        elif report is None:
            status, note = "unknown", "the report doesn't print this"
        elif report_flag:
            status, note = "unknown", f"the report figure is flagged: {report_flag}"
        else:
            d = (contract or 0) - report
            status = "match" if abs(d) < 0.005 else "rounding" if abs(d) <= 0.011 else "differs"
            note = {"match": "", "rounding": "1 cent apart: rounding"}.get(status, f"off by {d:,.2f}")
        lines.append({"line": label, "contract": None if contract is None else round(contract, 2), "report": report,
                      "status": status, "note": note})

    defs, pbc = res["definitions"], res["principal_by_class"]
    for n in rec.get("notes") or []:
        c, cl = ident(n["class"]), n["class"]
        if f"int_{c}" in given:
            lines.append({"line": f"{cl} interest", "contract": None, "report": n.get("interest_paid"), "status": "given",
                          "note": f"rate not fixed by the contract ({', '.join(sorted(missing & deps.get(f'int_{c}', {f'int_{c}'})))}): "
                                  "the report's figure is used to check the rest"})
        else:
            add(f"{cl} interest", defs.get(f"int_{c}"), n.get("interest_paid"), tainted(f"int_{c}"),
                rec_flags.get(f"notes[{c.upper()}].interest_paid"))
        add(f"{cl} principal", pbc.get(c, 0.0), n.get("principal_paid"), flow_unknown,
            rec_flags.get(f"notes[{c.upper()}].principal_paid"))
    if "servicing_fee" in defs:
        add("Servicing fee", defs["servicing_fee"], rec.get("servicing_fee"), tainted("servicing_fee"), rec_flags.get("servicing_fee"))
    resid = next((s["paid"] for s in res["steps"] if s["kind"] == "residual"), None)
    add("Released to residual holder", resid, rec.get("excess_to_residual"), flow_unknown, rec_flags.get("excess_to_residual"))
    return {"lines": lines, "steps": res["steps"]}
