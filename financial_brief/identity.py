"""Document subjects backed by exact source text, including older saved briefs."""
import re


def source_subject(source, proposed=None):
    text = source['text']
    name, ticker, quote = '', '', ''
    if proposed:
        name, ticker, quote = (str(proposed.get(k, '')).strip() for k in ('name','ticker','quote'))
        if not name or name not in quote or quote not in text or (ticker and ticker not in quote):
            name, ticker, quote = '', '', ''
    heading = re.search(r"^([A-Z][A-Z &.'(),/-]{3,100})\s+\(([A-Z0-9.-]{1,25})\)\s*$", text, re.M)
    legal = re.search(r"^([A-Z][A-Za-z0-9 &.,'()/-]{3,100}?(?:Limited|Ltd\.?|Inc\.?|Corporation|PLC|plc|Corp\.?))\s+(?:is engaged|operates|provides|is a|was founded)\b[^\n]*",text,re.M)
    signature=re.search(r"^For ([A-Z][A-Za-z0-9 &.,'()-]{2,100}?(?:Limited|Ltd\.?|Inc\.?|Corporation))\s*$",text,re.M)
    if not name and signature:
        name, quote = signature[1],signature[0]
    if not name and legal:
        name, quote = legal[1], legal[0]
    if not name and heading:
        name, ticker, quote = heading[1].strip(), heading[2], heading[0].strip()
    if name and not ticker and heading:
        compact=lambda value:re.sub(r'[^a-z0-9]','',value.casefold())
        if compact(name).startswith(compact(heading[1])):
            begin=text.find(quote)
            start,end=min(begin,heading.start()),max(begin+len(quote),heading.end())
            if end-start <= 3000:
                ticker=heading[2]
                quote=text[start:end].strip()
    if not name:
        return None
    return {'name':name,'ticker':ticker,'quote':quote,'file':source['file'],'page':source.get('page'),
            'section':source.get('section'),'source':source['id'],'label':'Document subject'}


def identify(sources, proposals=None):
    subjects, seen = [], set()
    for source in sources:
        if not all(source.get(key) for key in ('file','text','id')) or source['file'] in seen:continue
        subject=source_subject(source,(proposals or {}).get(source['id']))
        if subject:
            seen.add(source['file']);subject['id']=f'I{len(subjects)+1}';subjects.append(subject)
    return subjects
