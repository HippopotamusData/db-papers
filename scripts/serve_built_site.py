#!/usr/bin/env python3
"""Serve the existing acceptance artifact at the production URL prefix for tests."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).resolve().parents[1] / 'site'), **kwargs)

    def do_GET(self):
        if not urlsplit(self.path).path.startswith('/db-papers/'):
            self.send_error(404)
            return
        self.path = self.path[len('/db-papers'):]
        super().do_GET()


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8766), Handler).serve_forever()
