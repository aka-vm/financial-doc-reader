"""Report file -> text a model can read reliably.

HTML tables are rebuilt as a real grid (colspan, rowspan, stacked and group headers), and every value is written
with its row label and full column-header path:
    Net Credit Losses :: Current Period Only = $442,621.32 ; Cumulative > Current Period = $5,840,372.73
Text a reader can't see (display:none, zero-size fonts) is dropped. Plain .txt passes through; .pdf needs pypdf.
"""
import re
from html import unescape
from html.parser import HTMLParser

HIDDEN = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em|%)?\s*(?:;|$)", re.I)
VOID = {"br", "img", "hr", "input", "meta", "link", "col", "wbr", "area", "base", "source"}


def strip_hidden(src):
    """Remove elements a reader can't see (display:none, visibility:hidden, zero font size). Text a person can't see
    must never reach the model: it is the easiest place to hide instructions in a document."""
    out, depth, i = [], 0, 0
    for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*)>", src):
        closing, tag, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3)
        if depth == 0:
            out.append(src[i:m.start()])
        if depth:
            if tag in VOID or attrs.rstrip().endswith("/"):
                pass
            elif closing:
                depth -= 1
            else:
                depth += 1
        elif not closing and tag not in VOID and HIDDEN.search(attrs):
            depth = 1
        else:
            out.append(m.group(0))
        i = m.end()
    if depth == 0:
        out.append(src[i:])
    return "".join(out)


NUM = re.compile(r"^\$?\s*\(?-?\$?\s*(?:\d[\d,]*(?:\.\d+)?|\.\d+)\s*%?\)?$")
DASH = {"—", "–", "-"}
TAG = re.compile(r"^(?:\{\w+\}|\(\w\)|\d{1,3}\.(?!\d)|[a-z]\.)\s*")  # "{12}", "(a)", "12.", "a." line markers


class Grid(HTMLParser):
    """parts: ("text", str) and ("table", rows) where rows are lists of (text, colspan, rowspan)."""

    def __init__(self):
        super().__init__()
        self.parts, self.text, self.table, self.row, self.cell, self.span, self.depth = [], [], None, None, None, 1, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self._flush()
                self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
            a = dict(attrs)
            try:
                self.span = (max(1, min(30, int(a.get("colspan") or 1))), max(1, min(50, int(a.get("rowspan") or 1))))
            except ValueError:
                self.span = (1, 1)
        elif tag == "br":
            (self.cell if self.cell is not None else self.text).append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append((re.sub(r"\s+", " ", unescape("".join(self.cell)).replace("\xa0", " ")).strip(), *self.span))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table":
            self.depth -= 1
            if self.depth == 0 and self.table is not None:
                self.parts.append(("table", self.table))
                self.table = None
        elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4") and self.table is None:
            self.text.append("\n")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        elif self.table is None:
            self.text.append(data)

    def _flush(self):
        t = "".join(self.text)
        if t.strip():
            self.parts.append(("text", unescape(t)))
        self.text = []

    def close(self):
        super().close()
        self._flush()


def value(text):
    t = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if t in DASH:
        return 0.0
    neg = t.startswith("(") and t.endswith(")")
    try:
        v = float(t.strip("()").strip())
    except ValueError:
        return None
    return -v if neg else v


def is_value(text):
    return text in DASH or bool(NUM.match(text))


def expand(row, above):
    """Row of (text, colspan, rowspan) -> grid columns: (text, is_origin). `above` carries cells from earlier rows
    that span down into this one ({column: [rows left, text, colspan]}); they take their columns first, so the
    cells of this row land under the right headers."""
    out, cells = [], list(row)
    while cells or any(c >= len(out) for c in above):
        col = len(out)
        if col in above:
            left, text, span = above[col]
            out.extend((text, False) for _ in range(span))
            if left <= 1:
                del above[col]
            else:
                above[col][0] -= 1
        elif cells:
            text, span, rspan = cells.pop(0)
            if rspan > 1:
                above[col] = [rspan - 1, text, span]
            out.append((text, True))
            out.extend((text, False) for _ in range(span - 1))
        else:
            out.append(("", False))  # a gap before a spanning cell further right
    return out


def glue(row):
    """Fold ')' and '%' cells into the number before them: "$(45,235.79" + ")" -> "$(45,235.79)"."""
    row = list(row)
    for i, (t, *spans) in enumerate(row):
        if t in (")", "%"):
            k = next((k for k in range(i - 1, -1, -1) if row[k][0]), None)
            if k is not None:
                row[k], row[i] = (row[k][0] + t, *row[k][1:]), ("", *spans)
    return row


def walk(src):
    """(candidates, lines): every numeric table cell with its section / row label / column-header path, and a text
    rendering of the report in which each table value carries that header path ("Cumulative > Current Period = 5.8")."""
    g = Grid()
    g.feed(re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", strip_hidden(src)))
    g.close()
    out, lines, section, carried = [], [], "", []
    for kind, part in g.parts:
        if kind == "text":
            text = [x for x in (re.sub(r"\s+", " ", x).strip() for x in part.split("\n")) if x]
            lines += text
            heads = [x for x in text if not is_value(x)]
            if heads:
                section = heads[-1][:80]
            continue
        headers, last_was_data = [], False  # headers: (cells, start column if a column-group header else None)
        width, above = max((sum(c[1] for c in r) for r in part), default=0), {}
        for raw in part:
            cells = expand(glue(raw), above)
            texts = [t for t, o in cells if o and t and t not in ("$", "%", ")", "(")]
            if not texts:
                continue
            values = [j for j, (t, o) in enumerate(cells) if o and t not in ("$",) and is_value(t) and value(t) is not None]
            if not values:
                lines.append(" | ".join(texts))
                pair = len(texts) == 2 and cells[0][1] and cells[0][0] == texts[0]  # "label | value" from column 0
                if pair or texts[0].endswith(":") or any(not TAG.sub("", t) for t in texts):
                    continue  # "Distribution Date: | 08/18/2026", "{81} Trigger Occurred | No": a line, not a header
                first = next(j for j, (t, o) in enumerate(cells) if o and t and t not in ("$", "%", ")", "("))
                end = first + 1
                while end < len(cells) and not cells[end][1]:
                    end += 1
                # a lone text cell is a heading, unless it sits over some of the value columns only ("Cumulative"
                # spanning four of five period columns): then it is a column-group header
                group = len(texts) == 1 and first > 0 and end < width
                if len(texts) == 1 and not group:
                    section = TAG.sub("", texts[0])[:80]
                    if last_was_data:
                        headers = []  # a heading after data rows starts a new section with its own columns
                else:
                    h = (cells, first if group else None)
                    headers = [h] if last_was_data or not headers else headers + [h]
                last_was_data = False
                continue
            if not headers and carried and carried[0] == width:
                headers = carried[1]  # EDGAR splits one visual table across <table>s: inherit the headers
            last_was_data = True
            labels = [(j, TAG.sub("", t)) for j, (t, o) in enumerate(cells)
                      if o and t and not is_value(t) and t not in ("$", "%", ")", "(") and TAG.sub("", t)]
            first = labels[0][1] if labels and labels[0][0] < values[0] else ""
            label_col = labels[0][0] if first else -1
            items = []
            for j, (t, o) in enumerate(cells):
                if not o or j not in values:
                    if o and t and t not in ("$", "%", ")", "(") and not (first and j == label_col):
                        items.append(t)  # the rendering keeps labels exactly as printed
                    continue
                text = t
                near = next((t for k, t in reversed(labels) if k < j), "")
                row = first if near in ("", first) else f"{first} … {near}".strip(" …")
                path = []
                for h, gstart in headers:
                    if gstart is not None and gstart <= label_col:
                        continue  # a "group" over the row-label column is really a heading
                    if j < len(h) and h[j][0] and h[j][0] not in path and h[j][0] not in ("$", "%"):
                        path.append(h[j][0])
                col = " > ".join(path)
                items.append(f"{col} = {text}" if col else text)
                col = col or (f"value {values.index(j) + 1} of {len(values)}" if len(values) > 1 else "")
                out.append({"id": f"c{len(out)}", "section": section, "row": (row or section)[:120],
                            "col": col[:90], "text": text, "value": value(text)})
            lines.append(f"{cells[label_col][0]} :: " + " ; ".join(items) if first else " ; ".join(items))
        if headers:
            carried = (width, headers)
    return out, lines


def render(src):
    return "\n".join(walk(src)[1])


def to_text(path):
    if path.lower().endswith((".htm", ".html")):
        return render(open(path, encoding="utf-8", errors="replace").read())
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader  # optional: pip install pypdf
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    return open(path, encoding="utf-8", errors="replace").read()
