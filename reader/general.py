"""Any other document (a 10-K, an 8-K, a prospectus, a fund filing...) -> what it is, a short summary, and key facts.

Every fact carries the sentence it came from; code checks that the sentence is really in the document and that the
fact's numbers are in that sentence. A fact that fails is flagged, never shown as checked. The summary is the model's
own words and is labelled as such.
"""
import re

from .backends import call
from .convert import to_text

MAX_WORDS = 20000  # what a local model reads in one pass; longer documents say how much was read

PROMPT = """You are reading one document filed with the US SEC. Fill the JSON schema:
- document_type: what kind of document this is, in plain words (e.g. "annual report", "custody compliance statement").
- filer: who filed it or who it is about. date: its main date as YYYY-MM-DD, or null.
- summary: 3-5 plain sentences on what the document says and why it matters to a reader.
- facts: up to 15 of the most important specific facts (amounts, percentages, dates, parties, obligations, outcomes).
  For each: a short label, the value as written, and quote = the exact sentence or table row from the document that
  states it, copied character for character (no paraphrase, no ellipsis).
Use only what the document says."""

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["document_type", "filer", "date", "summary", "facts"],
          "properties": {"document_type": {"type": "string"}, "filer": {"type": "string"}, "date": {"type": ["string", "null"]},
                         "summary": {"type": "string"},
                         "facts": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                               "required": ["label", "value", "quote"],
                                                               "properties": {"label": {"type": "string"}, "value": {"type": "string"},
                                                                              "quote": {"type": "string"}}}}}}


def squash(t):
    return re.sub(r"[\s|]+", " ", t).strip().lower()


def numbers(t):
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", t)}


def check_fact(f, text):
    """'checked' when the quote is in the document and every number in the value is in the quote."""
    q = squash(f.get("quote", ""))
    if len(q) < 8 or q not in text:
        return "the quoted sentence was not found in the document"
    missing = numbers(f.get("value", "")) - numbers(q)
    if missing:
        return f"{', '.join(sorted(missing))} is not in the quoted sentence"
    return None


def read_document(path, backend, model=None, url=None, form=None):
    full = to_text(path)
    words = full.split()
    text = " ".join(words[:MAX_WORDS])
    got = call(backend, model, f"{PROMPT}\n\nDocument{f' (EDGAR form {form})' if form else ''}:\n{text}", SCHEMA, url)
    plain = squash(full)
    for f in got.get("facts", []):
        f["problem"] = check_fact(f, plain)
    return got | {"words": len(words), "read_words": min(len(words), MAX_WORDS), "form": form}
