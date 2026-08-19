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
        path_clean = self.path.split('?')[0]
        if path_clean == '/ideas':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            import json
            res = get_tradingview_ideas()
            self.wfile.write(json.dumps(res).encode('utf-8'))
        elif path_clean in ['/api/bybit/balance', '/api/bybit/positions', '/api/binance/balance', '/api/binance/positions']:
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
            if path_clean == '/api/bybit/balance':
                res = make_bybit_request('/v5/account/wallet-balance', {"accountType": "UNIFIED"}, api_key, api_secret)
                if isinstance(res, dict) and (res.get('retCode') == 10016 or 'Unified account' in res.get('retMsg', '')):
                    res = make_bybit_request('/v5/account/wallet-balance', {"accountType": "CONTRACT"}, api_key, api_secret)
            elif path_clean == '/api/bybit/positions':
                res = make_bybit_request('/v5/position/list', {"category": "linear", "settleCoin": "USDT"}, api_key, api_secret)
            elif path_clean == '/api/binance/balance':
                res = make_binance_request('/fapi/v2/balance', {}, api_key, api_secret)
            elif path_clean == '/api/binance/positions':
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
    import urllib.request
    import xml.etree.ElementTree as ET
    import re
    
    url = "https://cointelegraph.com/rss"
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )
    
    ideas = []
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            # Parse XML
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            
            for item in items:
                title = item.find('title').text if item.find('title') is not None else ""
                link = item.find('link').text if item.find('link') is not None else ""
                desc_raw = item.find('description').text if item.find('description') is not None else ""
                pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
                
                # Extract image URL from description HTML
                img_url = ""
                img_match = re.search(r'<img[^>]*src="([^"]+)"', desc_raw)
                if img_match:
                    img_url = img_match.group(1)
                
                # Clean HTML tags from description text
                desc_clean = re.sub(r'<[^>]+>', '', desc_raw).strip()
                desc_clean = re.sub(r'\s+', ' ', desc_clean)
                if len(desc_clean) > 200:
                    desc_clean = desc_clean[:200] + "..."
                
                # Determine strategy from keywords
                title_lower = title.lower()
                desc_lower = desc_clean.lower()
                strategy = "Neutral"
                if any(k in title_lower or k in desc_lower for k in ['bullish', 'bounce', 'rise', 'target', 'buy', 'long', 'rally', 'recovery']):
                    strategy = "Long"
                elif any(k in title_lower or k in desc_lower for k in ['bearish', 'drop', 'fall', 'crash', 'sell', 'short', 'dump', 'dip']):
                    strategy = "Short"
                
                # Determine Symbol
                symbol = "ALT"
                if 'bitcoin' in title_lower or 'btc' in title_lower:
                    symbol = "BTC"
                elif 'ethereum' in title_lower or 'eth' in title_lower:
                    symbol = "ETH"
                elif 'solana' in title_lower or 'sol' in title_lower:
                    symbol = "SOL"
                elif 'litecoin' in title_lower or 'ltc' in title_lower:
                    symbol = "LTC"
                
                ideas.append({
                    "title": title,
                    "link": link,
                    "description": desc_clean,
                    "image": img_url,
                    "author": "Cointelegraph",
                    "date": pub_date,
                    "strategy": strategy,
                    "symbol": symbol
                })
    except Exception as e:
        return {"ideas": [], "error": str(e)}
        
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
