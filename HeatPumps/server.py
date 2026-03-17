#!/usr/bin/env python3
"""
Heat Pump local proxy server.
Serves the webapp and proxies /api/<ip>/... -> http://<ip>/...
so the browser avoids CORS issues with the Daikin units.

Usage:  python server.py
Then open: http://localhost:8080
"""

import http.server
import urllib.request
import os
import sys

PORT = 8765
SERVE_DIR = os.path.dirname(os.path.abspath(__file__))


class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path.startswith('/api/'):
            self._proxy()
        else:
            super().do_GET()

    def _proxy(self):
        # self.path is like: /api/192.168.55.122/aircon/get_control_info
        remainder = self.path[5:]           # strip '/api/'
        slash = remainder.find('/')
        if slash == -1:
            self.send_error(400, 'Missing path after IP')
            return
        ip   = remainder[:slash]
        rest = remainder[slash + 1:]        # e.g. aircon/get_control_info?...
        target = f'http://{ip}/{rest}'
        try:
            with urllib.request.urlopen(target, timeout=6) as resp:
                body = resp.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_error(502, f'Proxy error: {e}')


if __name__ == '__main__':
    os.chdir(SERVE_DIR)
    server = http.server.HTTPServer(('', PORT), ProxyHandler)
    print(f'Heat Pump dashboard -> http://localhost:{PORT}')
    print('Press Ctrl+C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
        sys.exit(0)
