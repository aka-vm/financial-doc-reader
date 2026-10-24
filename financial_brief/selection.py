"""Prioritize material figures without changing their values or metric definitions."""
import re

CATEGORIES=[
 ('revenue',r'revenue|net sales|gross sales|income from operations'),
 ('profit',r'profit|net income|\bPAT\b|earnings after tax'),
 ('operating earnings',r'EBITDA|operating income|operating earnings'),
 ('cash flow',r'cash flow|cash generated|cash from operations'),
 ('debt',r'net debt|outstanding debt|total debt|borrowings|net worth|capital ratio|\bCET1\b'),
 ('investment',r'capital expenditure|\bcapex\b|capital spending|loan.to.deposit|credit.to.deposit'),
 ('margin',r'margin|\bNIM\b|return on assets|\bROA\b'),
 ('cash',r'cash and|cash &|cash balance|liquidity'),
]


def materiality(fact):
    label=fact.get('label','')
    family=next((name for name,pattern in CATEGORIES if re.search(pattern,label,re.I)),label.casefold())
    score=15 if family in {name for name,_ in CATEGORIES} else 0
    if re.search(r'consolidated|group',label,re.I):score+=12
    if re.search(r'standalone|segment|\bJPL\b|\bJio\b|\bRRVL\b|\bO2C\b',label,re.I):score-=4
    if re.search(r'brokerage.*(?:drop|declin|fall)|(?:drop|declin|fall).*brokerage',label,re.I):score+=10
    if re.search(r'registration|scrip code|telephone|fax|CIN\b|anniversary|years since',label,re.I):score-=30
    if re.search(r'forecast|expected|proposed|target',label,re.I):score-=4
    if re.search(r'whose financial|other auditors?|not (?:audited|reviewed)|unaudited subsidiaries',
                 fact.get('quote','')+' '+label,re.I):score-=40
    years=re.findall(r'20\d{2}',fact.get('period',''))
    fiscal=re.search(r'FY\s*(\d{2})(?:[/-](\d{2}))?(?!\d)',fact.get('period',''),re.I)
    year=max(map(int,years),default=(2000+int(fiscal[2] or fiscal[1]) if fiscal else 0))
    return score,year,family


def select_figures(facts,limit=6):
    candidates=[f for f in facts if re.search(r'\d',f.get('value','')) and not f.get('context_problem')]
    ranked=sorted(enumerate(candidates),key=lambda pair:(*materiality(pair[1])[:2],-pair[0]),reverse=True)
    selected,seen=[],set()
    for _,fact in ranked:
        score,_,family=materiality(fact)
        key=(fact.get('file'),family)
        if score <= 0 or key in seen:continue
        seen.add(key);selected.append(fact)
        if len(selected)==limit:break
    return selected
