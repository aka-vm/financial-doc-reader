"""Build optional comparison charts from source-matched facts without model calls."""
import math
import re
from collections import defaultdict

CURRENCIES = {'$': '$', 'USD': 'USD', '€': 'EUR', 'EUR': 'EUR', '£': 'GBP', 'GBP': 'GBP',
              'INR': 'INR', '₹': 'INR', 'RS': 'Rs'}
VALUE = re.compile(r'^(?P<prefix>USD|EUR|GBP|INR|Rs|[$€£₹])?\s*(?P<number>-?\d+(?:,\d{3})*(?:\.\d+)?|\(\d+(?:,\d{3})*(?:\.\d+)?\))\s*(?P<scale>thousand|million|billion|crore|lakh)?\s*(?P<percent>%)?$', re.I)


def measurement(fact):
    normalize=lambda text: re.sub(r'\bRs\.?\s*', 'Rs ', re.sub(r'\bcrores\b', 'crore', re.sub(r'\blakhs\b', 'lakh', text, flags=re.I), flags=re.I), flags=re.I)
    match = VALUE.fullmatch(normalize(fact.get('value', '').strip()))
    if not match:
        return None
    unit = normalize(fact.get('unit', '').strip())
    # Only explicitly understood units can be compared; no currency or scale conversion.
    tokens = re.findall(r'USD|EUR|GBP|INR|Rs|[$€£₹]|thousand|million|billion|crore|lakh|%|percent|percentage|points', unit, re.I)
    remainder = re.sub(r'USD|EUR|GBP|INR|Rs|[$€£₹]|thousand|million|billion|crore|lakh|%|percent|percentage|points|\s', '', unit, flags=re.I)
    if remainder:
        return None
    currencies = {CURRENCIES[t.upper()] for t in [match['prefix'], *tokens] if t and t.upper() in CURRENCIES}
    scales = {t.lower() for t in [match['scale'], *tokens] if t and t.lower() in {'thousand','million','billion','crore','lakh'}}
    if len(currencies) > 1 or len(scales) > 1:
        return None
    percent = bool(match['percent']) or any(t.lower() in {'%', 'percent', 'percentage'} for t in tokens)
    if (percent and (currencies or scales)) or (not percent and not currencies):
        return None
    numeric = match['number'].replace(',', '')
    value = -float(numeric[1:-1]) if numeric.startswith('(') else float(numeric)
    if not math.isfinite(value):
        return None
    label = '%' if percent else ' '.join([*sorted(currencies), *sorted(scales)])
    # Percentage points are a distinct unit from percent.
    if any(t.lower() == 'points' for t in tokens):
        label += ' points'
    return value, label


def period_order(period):
    """Sort explicit fiscal/quarter labels without relabeling them as calendar years."""
    value=re.sub(r"\s+", "", period.upper())
    if re.fullmatch(r"20\d{2}",value):return 'calendar-year',int(value)
    match=re.fullmatch(r"FY(20\d{2}|\d{2})",value)
    if match:return 'fiscal-year',int(match[1]) if len(match[1])==4 else 2000+int(match[1])
    match=re.fullmatch(r"(?:Q([1-4])|([1-4])Q)FY(20\d{2}|\d{2})",value)
    if match:return 'fiscal-quarter',(int(match[3]) if len(match[3])==4 else 2000+int(match[3]))*4+int(match[1] or match[2])
    return None


def build_views(facts):
    usable = [f for f in facts if not f.get('context_problem')
              and len(f.get('value', '')) <= 120
              and re.search(r'(?<!\w)\d', f.get('value', ''))]
    rows = [{k: f.get(k, '') for k in ('id', 'label', 'value', 'period', 'unit', 'file', 'context_reviewed')} for f in usable[:40]]
    groups = defaultdict(dict)
    conflicts = set()
    for fact in usable:
        if fact.get("context_reviewed") is False:continue
        period = fact.get('period', '').strip()
        parsed = measurement(fact)
        order=period_order(period)
        if order is None or parsed is None:
            continue
        label = re.sub(r'\b20\d{2}\b|\b(?:in|for|FY)\b', '', fact['label'], flags=re.I)
        label = re.sub(r'\s+', ' ', label).strip(' -:()')
        if not label:
            continue
        value, unit = parsed
        key = (fact['file'], fact.get('source', ''), label.casefold(), unit, order[0])
        existing = groups[key].get(period)
        if existing and existing['number'] != value:
            conflicts.add(key)
        groups[key][period] = {'period': period, 'number': value, 'value': fact['value'], 'evidence': [fact['id']], 'label': label}
    charts = []
    for key, points in groups.items():
        if key in conflicts or not 2 <= len(points) <= 6:
            continue
        ordered = sorted(points.values(), key=lambda point: period_order(point['period'])[1])
        charts.append({'title': ordered[0]['label'], 'unit': key[3], 'file': key[0], 'points': ordered})
        if len(charts) == 3:
            break
    return {'rows': rows, 'total_rows': len(usable), 'charts': charts}
