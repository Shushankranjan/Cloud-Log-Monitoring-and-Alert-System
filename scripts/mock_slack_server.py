#!/usr/bin/env python3
"""A tiny HTTP server that acts as a fake Slack webhook endpoint."""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    captured = []

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = body

        Handler.captured.append(payload)
        print(json.dumps({"count": len(Handler.captured), "payload": payload}), flush=True)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if self.path == "/messages":
            self.wfile.write(json.dumps(Handler.captured).encode("utf-8"))
        else:
            self.wfile.write(b'{"status": "ok"}')

    def log_message(self, format, *args):
        # Suppress default access logs; we print JSON above.
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Mock Slack server listening on port {port}", flush=True)
    server.serve_forever()
