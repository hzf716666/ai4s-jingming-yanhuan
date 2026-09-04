"""Temp CORS HTTP server so the browser page (console.cloud.tencent.com) can fetch
the zip bytes from localhost and inject them into the COS upload control."""
import http.server
import os

ROOT = r"E:\tb"
PORT = 9000


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
