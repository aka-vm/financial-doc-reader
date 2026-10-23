"""Drop-in web page: drag a servicer report onto it, get the standard figures with anything doubtful flagged.

usage: python3 app.py [--backend ollama --model qwen3.5:9b] [--url URL] [--port 8420]
The backend and model can also be changed on the page. Nothing is stored; uploads go to a temp file and are deleted.
"""
import argparse
import json
import os
import sys
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reader.extract import read_report  # noqa: E402

UI = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "reader", "ui.html"), encoding="utf-8").read()
DEFAULTS = {}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/defaults":
            return self.send(200, json.dumps(DEFAULTS))
        self.send(200, UI, "text/html; charset=utf-8")

    def do_POST(self):
        if not self.path.startswith("/api/read"):
            return self.send(404, "{}")
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
        name = os.path.basename(self.headers.get("X-Filename", "report.htm"))
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in (".htm", ".html", ".txt", ".pdf"):
            return self.send(400, json.dumps({"error": "upload an .htm, .html, .txt or .pdf servicer report"}))
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, name)
            open(path, "wb").write(body)
            try:
                res = read_report(path, q.get("backend") or DEFAULTS["backend"], q.get("model") or DEFAULTS.get("model"),
                                  q.get("url") or DEFAULTS.get("url"))
            except Exception as e:  # show the reason on the page instead of a blank failure
                return self.send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))
        self.send(200, json.dumps(res))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="ollama")
    ap.add_argument("--model")
    ap.add_argument("--url")
    ap.add_argument("--port", type=int, default=8420)
    a = ap.parse_args()
    DEFAULTS.update(backend=a.backend, model=a.model, url=a.url)
    print(f"open http://localhost:{a.port}  (backend {a.backend}, model {a.model or 'default'})")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
