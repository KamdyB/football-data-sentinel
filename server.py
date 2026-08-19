import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline import run_pipeline

MAX_BODY_BYTES = 5 * 1024 * 1024  # 5MB guard against a malformed or runaway payload


class IngestionEndpoint(BaseHTTPRequestHandler):

    def send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"service": "football-data-sentinel", "status": "ok"})
            return

        self.send_json(404, {"error": "route not found"})

    def do_POST(self):
        if self.path != "/api/process":
            self.send_json(404, {"error": "route not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_json(400, {"error": "invalid Content-Length header"})
            return

        if length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "payload too large"})
            return

        try:
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))

            report = run_pipeline(data)

            self.send_json(200, report)

        except json.JSONDecodeError:
            self.send_json(400, {"error": "request body is not valid JSON"})

        except (ValueError, TypeError) as error:
            self.send_json(400, {"error": str(error)})

        except Exception:
            # Full trace goes to the server's own stderr so you can actually
            # debug a live failure. The client only ever sees a generic
            # message, since a stack trace is not something to expose
            # over the wire.
            traceback.print_exc(file=sys.stderr)
            self.send_json(500, {"error": "internal pipeline failure"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), IngestionEndpoint).serve_forever()