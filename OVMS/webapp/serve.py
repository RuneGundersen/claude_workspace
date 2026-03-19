"""Simple dev server for OVMS webapp."""
import http.server, socketserver, webbrowser, os

PORT = 8080
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Suppress request logging

import socket
host = socket.gethostname()
print(f"OVMS Dashboard running at: http://{host}:{PORT}")
print("Press Ctrl+C to stop.\n")
# Only open browser when running interactively on a desktop
if os.environ.get('DISPLAY') or os.name == 'nt':
    webbrowser.open(f"http://localhost:{PORT}")

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
