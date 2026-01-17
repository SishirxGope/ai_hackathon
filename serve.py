#!/usr/bin/env python3
"""
Simple HTTP server for the Trustworthy AI Dashboard
Run: python serve.py
Then open: http://localhost:8000/ui/index.html
"""

import http.server
import socketserver
import os
from pathlib import Path

PORT = 8000
HANDLER = http.server.SimpleHTTPRequestHandler

# Change to workspace directory
os.chdir(Path(__file__).parent)

with socketserver.TCPServer(("", PORT), HANDLER) as httpd:
    print(f"Server running at http://localhost:{PORT}")
    print(f"Dashboard: http://localhost:{PORT}/ui/public/index.html")
    print(f"Press Ctrl+C to stop")
    httpd.serve_forever()
