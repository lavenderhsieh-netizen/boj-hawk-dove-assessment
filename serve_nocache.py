#!/usr/bin/env python3
"""Static server that disables browser caching so laptops never serve a stale
dashboard. Same behaviour as `python3 -m http.server` but every response carries
no-store/no-cache headers, and text/JSON responses are gzip-compressed when the
client supports it. Binds to the PORT env var (default 8502)."""
import gzip
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
COMPRESSIBLE_EXT = {".json", ".html", ".htm", ".js", ".css", ".txt", ".svg", ".md"}


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        path = self.translate_path(self.path.split("?", 1)[0])
        ext = os.path.splitext(path)[1].lower()
        accept_enc = self.headers.get("Accept-Encoding", "")
        if ext in COMPRESSIBLE_EXT and "gzip" in accept_enc and os.path.isfile(path):
            try:
                with open(path, "rb") as f:
                    raw = f.read()
            except OSError:
                return super().do_GET()
            body = gzip.compress(raw, compresslevel=6)
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def main():
    port = int(os.environ.get("PORT", "8502"))
    handler = partial(NoCacheHandler, directory=DIRECTORY)
    with ThreadingHTTPServer(("0.0.0.0", port), handler) as httpd:
        print(f"Serving {DIRECTORY} on 0.0.0.0:{port} with no-cache headers + gzip")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
