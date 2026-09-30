"""Receptor local: el navegador envía por POST las filas extraídas y se guardan en JSONL."""
import http.server
import json
import sys

SALIDA = sys.argv[1]


class H(http.server.BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        with open(SALIDA, "a", encoding="utf-8") as f:
            f.write(json.dumps(datos, ensure_ascii=False) + "\n")
        self.send_response(200)
        self._cors()
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        # Navegación con los datos en ?d=<json>: la página no puede hacer fetch a localhost.
        import urllib.parse as up
        q = up.parse_qs(up.urlparse(self.path).query)
        if "d" in q:
            with open(SALIDA, "a", encoding="utf-8") as f:
                f.write(q["d"][0] + "\n")
            self.send_response(302)  # URL corta en la pestaña
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"guardado {len(q.get('d', [''])[0])} bytes".encode())

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
