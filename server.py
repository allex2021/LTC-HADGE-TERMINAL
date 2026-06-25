import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import sys
import os

PORT = 8000

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def handle_proxy(self, method):
        prefix = '/proxy/'
        if not self.path.startswith(prefix):
            self.send_error(400, "Bad Request: Missing proxy prefix")
            return

        target_url = urllib.parse.unquote(self.path[len(prefix):])
        
        body = None
        if method in ['POST', 'PUT', 'DELETE']:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length)

        headers = {}
        for key, val in self.headers.items():
            k_low = key.lower()
            if k_low not in ['host', 'content-length', 'connection', 'origin', 'referer', 'accept-encoding']:
                headers[key] = val

        req = urllib.request.Request(
            target_url,
            data=body,
            headers=headers,
            method=method
        )

        try:
            with urllib.request.urlopen(req) as response:
                res_body = response.read()
                self.send_response(response.status)
                
                for k, v in response.headers.items():
                    if k.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'access-control-allow-origin']:
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(res_body)
        except urllib.error.HTTPError as e:
            res_body = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'access-control-allow-origin']:
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(res_body)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def do_GET(self):
        if self.path.startswith('/proxy/'):
            self.handle_proxy('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/proxy/'):
            self.handle_proxy('POST')
        else:
            super().do_POST()

    def do_PUT(self):
        if self.path.startswith('/proxy/'):
            self.handle_proxy('PUT')
        else:
            super().do_PUT()

    def do_DELETE(self):
        if self.path.startswith('/proxy/'):
            self.handle_proxy('DELETE')
        else:
            super().do_DELETE()

if __name__ == '__main__':
    # Ensure we serve files from server.py's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir:
        os.chdir(script_dir)
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ProxyHTTPRequestHandler) as httpd:
        print(f"Starting LTC-HADGE-TERMINAL CORS Proxy Server on http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            sys.exit(0)
