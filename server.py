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
        elif self.path in ['/api/bybit/balance', '/api/bybit/positions', '/api/binance/balance', '/api/binance/positions']:
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            api_key = self.headers.get('X-Api-Key', '')
            api_secret = self.headers.get('X-Api-Secret', '')
            
            if not api_key or not api_secret:
                import json
                self.wfile.write(json.dumps({"error": "Missing API Key or API Secret headers"}).encode('utf-8'))
                return
                
            import json
            res = {"error": "Invalid Path"}
            if self.path == '/api/bybit/balance':
                res = make_bybit_request('/v5/account/wallet-balance', {"accountType": "UNIFIED"}, api_key, api_secret)
                if isinstance(res, dict) and (res.get('retCode') == 10016 or 'Unified account' in res.get('retMsg', '')):
                    res = make_bybit_request('/v5/account/wallet-balance', {"accountType": "CONTRACT"}, api_key, api_secret)
            elif self.path == '/api/bybit/positions':
                res = make_bybit_request('/v5/position/list', {"category": "linear", "settleCoin": "USDT"}, api_key, api_secret)
            elif self.path == '/api/binance/balance':
                res = make_binance_request('/fapi/v2/balance', {}, api_key, api_secret)
            elif self.path == '/api/binance/positions':
                res = make_binance_request('/fapi/v2/positionRisk', {}, api_key, api_secret)
            
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
        # Title and Link (order-independent)
        title_tag_match = re.search(r'(<a\b[^>]*data-qa-id="ui-lib-card-link-title"[^>]*>)(.*?)</a>', art, re.DOTALL)
        if not title_tag_match:
            continue
        tag_attrs = title_tag_match.group(1)
        title_html = title_tag_match.group(2)
        
        title = re.sub(r'<[^>]+>', '', title_html).strip()
        href_match = re.search(r'href="([^"]+)"', tag_attrs)
        link = href_match.group(1) if href_match else ""
        if not link.startswith('http'):
            link = 'https://www.tradingview.com' + link
        
        # Description / Paragraph (order-independent)
        para_tag_match = re.search(r'<a\b[^>]*data-qa-id="ui-lib-card-link-paragraph"[^>]*>(.*?)</a>', art, re.DOTALL)
        para = ""
        if para_tag_match:
            para_html = para_tag_match.group(1)
            para = re.sub(r'<[^>]+>', '', para_html).strip()
            para = re.sub(r'\s+', ' ', para)
            
        # Image (extract actual chart image from the image link block)
        img_url = ""
        img_container = re.search(r'data-qa-id="ui-lib-card-link-image"[^>]*>(.*?)</a>', art, re.DOTALL)
        if img_container:
            img_match = re.search(r'<img[^>]*src="([^"]+)"', img_container.group(1))
            if img_match:
                img_url = img_match.group(1)
        if not img_url:
            # Fallback to any img tag if link image not found
            img_match = re.search(r'<img[^>]*src="([^"]+)"', art)
            img_url = img_match.group(1) if img_match else ""
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
            
        # Author / User
        author_match = re.search(r'/u/([^/]+)/', art)
        author = author_match.group(1).strip() if author_match else "Unknown"
            
        # Date
        time_match = re.search(r'dateTime="([^"]+)"', art)
        pub_date = time_match.group(1) if time_match else ""
            
        # Strategy
        strategy = "Neutral"
        if 'title="Long"' in art or 'strategyLong-' in art:
            strategy = "Long"
        elif 'title="Short"' in art or 'strategyShort-' in art:
            strategy = "Short"
            
        # Symbol
        symbol = ""
        symbol_icon_match = re.search(r'(<a\b[^>]*data-qa-id="ui-lib-card-preview-link-icon"[^>]*>)', art, re.DOTALL)
        if symbol_icon_match:
            icon_attrs = symbol_icon_match.group(1)
            title_attr = re.search(r'title="([^"]+)"', icon_attrs)
            if title_attr:
                symbol = title_attr.group(1).strip()
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

def make_bybit_request(path, query_params, api_key, api_secret):
    import hmac
    import hashlib
    import time
    import json
    import urllib.request
    import urllib.parse
    
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    
    query_string = urllib.parse.urlencode(sorted(query_params.items()))
    
    param_str = timestamp + api_key + recv_window + query_string
    sig = hmac.new(
        api_secret.encode('utf-8'),
        param_str.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    url = f"https://api.bybit.com{path}"
    if query_string:
        url += f"?{query_string}"
        
    req = urllib.request.Request(url, method="GET")
    req.add_header("X-BAPI-API-KEY", api_key)
    req.add_header("X-BAPI-TIMESTAMP", timestamp)
    req.add_header("X-BAPI-RECV-WINDOW", recv_window)
    req.add_header("X-BAPI-SIGN", sig)
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body)
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8')
            return {"error": e.code, "details": json.loads(err_body)}
        except:
            return {"error": e.code, "message": str(e)}
    except Exception as e:
        return {"error": 500, "message": str(e)}

def make_binance_request(path, query_params, api_key, api_secret):
    import hmac
    import hashlib
    import time
    import json
    import urllib.request
    import urllib.parse
    
    timestamp = str(int(time.time() * 1000))
    query_params["timestamp"] = timestamp
    query_params["recvWindow"] = "5000"
    
    query_string = urllib.parse.urlencode(query_params)
    sig = hmac.new(
        api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    url = f"https://fapi.binance.com{path}?{query_string}&signature={sig}"
    
    req = urllib.request.Request(url, method="GET")
    req.add_header("X-MBX-APIKEY", api_key)
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode('utf-8')
            return json.loads(res_body)
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8')
            return {"error": e.code, "details": json.loads(err_body)}
        except:
            return {"error": e.code, "message": str(e)}
    except Exception as e:
        return {"error": 500, "message": str(e)}

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
