#!/usr/bin/env python3
"""Static server that disables browser caching so laptops never serve a stale
dashboard. Same behaviour as `python3 -m http.server` but every response carries
no-store/no-cache headers. Binds to the PORT env var (default 8502)."""
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial

DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main():
    port = int(os.environ.get("PORT", "8502"))
    handler = partial(NoCacheHandler, directory=DIRECTORY)
    with ThreadingHTTPServer(("0.0.0.0", port), handler) as httpd:
        print(f"Serving {DIRECTORY} on 0.0.0.0:{port} with no-cache headers")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
