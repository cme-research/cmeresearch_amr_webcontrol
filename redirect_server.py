#!/usr/bin/env python3

# Simple HTTP redirect server for port 80 -> port 8000
# Listens on port 80 and redirects all requests to the same host on port 8000.

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit

class RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get('Host', '')
        # Extract hostname without port if present
        hostname = host.split(':')[0] if host else ''
        # Fallback to server address if Host header missing
        if not hostname:
            try:
                hostname = self.server.server_address[0]
            except Exception:
                hostname = 'localhost'
        target = f"http://{hostname}:8000{self.path}"
        self.send_response(301)
        self.send_header('Location', target)
        self.end_headers()

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        return self.do_GET()

    def log_message(self, format, *args):
        # Quiet logging to avoid cluttering container logs
        return


def run():
    server_address = ('', 80)
    httpd = HTTPServer(server_address, RedirectHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    run()
