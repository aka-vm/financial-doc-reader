"""Anything a user drops in -> a list of documents, each tagged with what it is.

Accepts report / contract files (.htm .html .txt .pdf), loan tapes (.csv, ABS-EE .xml), .zip archives of any of
these, and links: an EDGAR filing, a document, or a trust (a URL with its CIK, or "CIK 2003263"), which pulls the
deal's contracts and its latest monthly reports and loan tape.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html import unescape
from html.parser import HTMLParser

# SEC asks automated clients to identify themselves: set SEC_USER_AGENT="Your Name you@example.com"
UA = os.environ.get("SEC_USER_AGENT", "servicer-report-reader contact@example.com")
KEEP = (".htm", ".html", ".txt", ".pdf", ".csv", ".xml")
MAX_UNZIPPED = 500 << 20  # refuse zip bombs


def get(url, dst=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for wait in (0.2, 2, 5, 10, 20):  # SEC allows 10 requests a second and answers 503/429 to bursts: back off
        time.sleep(wait)
        try:
            r = urllib.request.urlopen(req, timeout=120)
            break
        except urllib.error.HTTPError as e:
            if e.code == 403 and "sec.gov" in url:
                raise RuntimeError("SEC refused the download: set SEC_USER_AGENT to your name and email, "
                                   "e.g. export SEC_USER_AGENT='Jane Doe jane@example.com'") from e
            if e.code not in (429, 503) or wait == 20:
                raise
    with r:
        if dst is None:
            return r.read()
        with open(dst, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    return dst


class _Index(HTMLParser):
    """Document rows (description, file, type, link) of an EDGAR filing index page."""

    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell, self.href = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row, self.href = [], None
        elif tag == "td" and self.row is not None:
            self.cell = ""
        elif tag == "a" and self.cell is not None:
            self.href = dict(attrs).get("href")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == "td" and self.row is not None and self.cell is not None:
            self.row.append(self.cell.strip())
            self.cell = None
        elif tag == "tr" and self.row and len(self.row) >= 4 and self.href:
            self.rows.append({"doc": self.row[2].split()[0] if self.row[2] else "", "type": self.row[3], "href": self.href})
            self.row = None


def filing_docs(cik, acc):
    p = _Index()
    p.feed(get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.html").decode("utf-8", "replace"))
    return [r for r in p.rows if r["doc"].lower().endswith(KEEP)]


def fetch_trust(cik, folder, months=2, log=print):
    """A deal's closing contracts (8-K exhibits), its last `months` servicer reports (10-D) and latest loan tape."""
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
    r = sub["filings"]["recent"]
    filings = sorted((dict(zip(r, v)) for v in zip(*r.values())), key=lambda f: f["filingDate"])
    log(f"{sub['name']}: {len(filings)} filings on EDGAR")
    out = []
    eightks = [f for f in filings if f["form"] == "8-K"]
    seen = set()
    for f in eightks[:3]:  # the closing-date 8-Ks carry the indenture, sale and servicing agreement, ...
        for row in filing_docs(cik, f["accessionNumber"]):
            if re.match(r"EX-(4|10|99)", row["type"]) and row["type"] not in seen:
                seen.add(row["type"])
                out.append(get("https://www.sec.gov" + row["href"], os.path.join(folder, f"{row['type'].lower()}.htm")))
    for f in [f for f in filings if f["form"] == "10-D"][-months:]:
        for row in filing_docs(cik, f["accessionNumber"]):
            if row["type"].startswith("EX-99"):
                out.append(get("https://www.sec.gov" + row["href"], os.path.join(folder, f"{f['reportDate']}_{row['type'].lower()}.htm")))
    tapes = [f for f in filings if f["form"] == "ABS-EE"]
    if tapes:
        for row in filing_docs(cik, tapes[-1]["accessionNumber"]):
            if row["type"] == "EX-102":
                out.append(get("https://www.sec.gov" + row["href"], os.path.join(folder, f"{tapes[-1]['reportDate']}_tape.xml")))
    log(f"downloaded {len(out)} documents")
    return out


def fetch_url(url, folder, log=print):
    cik = re.search(r"(?:CIK=?|/edgar/data/)\s*0*(\d{4,10})", url, re.I)
    acc = re.search(r"/(\d{10}-?\d{2}-?\d{6})", url)
    if cik and "sec.gov" in url or re.fullmatch(r"\s*CIK\s*\d+\s*", url, re.I):
        cik = cik or re.search(r"(\d+)", url)
        if acc and url.lower().endswith(("index.htm", "index.html", "/")):
            a = acc.group(1).replace("-", "")
            a = f"{a[:10]}-{a[10:12]}-{a[12:]}"
            return [get("https://www.sec.gov" + r["href"], os.path.join(folder, os.path.basename(r["href"])))
                    for r in filing_docs(cik.group(1), a)]
        if not url.lower().split("?")[0].endswith(KEEP):
            return fetch_trust(cik.group(1), folder, log=log)
    name = os.path.basename(urllib.parse.urlparse(url).path) or "download.htm"
    return [get(url, os.path.join(folder, name))]


def unzip(path, folder):
    out, total = [], 0
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = os.path.basename(info.filename)  # flatten: no paths from the archive are trusted
            if info.is_dir() or not name.lower().endswith(KEEP + (".zip",)) or name.startswith("."):
                continue
            total += info.file_size
            if total > MAX_UNZIPPED:
                raise ValueError("archive expands to more than 500 MB")
            dst = os.path.join(folder, name)
            with z.open(info) as src, open(dst, "wb") as f:
                f.write(src.read())
            out += unzip(dst, folder) if name.lower().endswith(".zip") else [dst]
    return out


def classify(path):
    """servicer_report | contract | prospectus | loan_tape | other, from measurable traits of the text: servicer
    reports are short and dense with amounts, prospectuses long and numeric, contracts cite "Section x.y" often."""
    low = path.lower()
    head = open(path, "rb").read(4000).decode("utf-8", "replace")
    if low.endswith(".xml") and "assetNumber" in open(path, "rb").read(200_000).decode("utf-8", "replace") \
            or low.endswith(".csv") and re.search(r"(?i)loan|balance|asset", head):
        return "loan_tape"
    if low.endswith(".pdf"):
        from .convert import to_text
        t = to_text(path)
    else:
        t = open(path, encoding="utf-8", errors="replace").read()
        t = unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)))
    t = re.sub(r"\s+", " ", t)
    words = max(1, len(t.split()))
    amounts = len(re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d\d)?|\d+\.\d\d\b", t)) / words
    sections = 1000 * len(re.findall(r"(?i)\bsection \d+\.\d+", t)) / words
    if words < 5000 and amounts >= 0.06:
        return "servicer_report"
    if words > 40000 and amounts >= 0.02:
        return "prospectus"
    if sections >= 2 and words >= 2000:
        return "contract"
    return "other"


def collect(files, links, folder, log=print):
    """files: local paths (uploads); links: URLs or 'CIK n'. Returns [{path, name, kind}]."""
    paths = []
    for p in files:
        paths += unzip(p, folder) if p.lower().endswith(".zip") else [p]
    for u in links:
        log(f"fetching {u}")
        paths += fetch_url(u.strip(), folder, log)
    docs = [{"path": p, "name": os.path.basename(p), "kind": classify(p)} for p in paths]
    for d in docs:
        log(f"{d['name']}: {d['kind'].replace('_', ' ')}")
    return docs
