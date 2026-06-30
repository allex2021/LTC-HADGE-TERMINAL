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
        if self.path == '/ideas':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            import json
            res = get_tradingview_ideas()
            self.wfile.write(json.dumps(res).encode('utf-8'))
        elif self.path.startswith('/proxy/'):
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

def get_tradingview_ideas():
    import re
    url = "https://www.tradingview.com/markets/cryptocurrencies/ideas/?sort=recent"
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        return {"ideas": [], "error": str(e)}

    articles = re.findall(r'<article\b[^>]*>(.*?)</article>', html, re.DOTALL)
    
    ideas = []
    for art in articles:
        title_match = re.search(r'data-qa-id="ui-lib-card-link-title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', art, re.DOTALL)
        if not title_match:
            continue
        link = title_match.group(1)
        if not link.startswith('http'):
            link = 'https://www.tradingview.com' + link
        title = re.sub(r'<[^>]+>', '', title_match.group(2)).strip()
        
        para_match = re.search(r'data-qa-id="ui-lib-card-link-paragraph"[^>]*>(.*?)</a>', art, re.DOTALL)
        para = ""
        if para_match:
            para = re.sub(r'<[^>]+>', '', para_match.group(1)).strip()
            para = re.sub(r'\s+', ' ', para)
            
        img_match = re.search(r'<img[^>]*src="([^"]+)"', art)
        img_url = ""
        if img_match:
            img_url = img_match.group(1)
            
        author_match = re.search(r'data-qa-id="ui-lib-card-link-author"[^>]*>.*?href="[^"]+"[^>]*>.*?by\s+([^<]+)</a>', art, re.DOTALL)
        author = "Unknown"
        if author_match:
            author = author_match.group(1).strip()
            
        time_match = re.search(r'dateTime="([^"]+)"', art)
        pub_date = ""
        if time_match:
            pub_date = time_match.group(1)
            
        strategy = "Neutral"
        if 'strategyLong-' in art or 'title="Long"' in art:
            strategy = "Long"
        elif 'strategyShort-' in art or 'title="Short"' in art:
            strategy = "Short"
            
        symbol_match = re.search(r'title="([^"]+)"\s+data-qa-id="ui-lib-card-preview-link-icon"', art)
        symbol = ""
        if symbol_match:
            symbol = symbol_match.group(1).strip()
            if ':' in symbol:
                symbol = symbol.split(':')[1]
        
        ideas.append({
            "title": title,
            "link": link,
            "description": para,
            "image": img_url,
            "author": author,
            "date": pub_date,
            "strategy": strategy,
            "symbol": symbol
        })
    return {"ideas": ideas}

if __name__ == '__main__':
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
