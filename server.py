import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pipeline import run_pipeline

class IngestionEndpoint(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/api/process":
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                report = run_pipeline(data)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(report).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"system_error": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), IngestionEndpoint).serve_forever()
