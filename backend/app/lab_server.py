"""Real loopback HTTP development app, with a finite, versioned response catalog."""

import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.testing.demo import response_for
from app.testing.local_policy import CATALOG_PATHS


class LabHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in CATALOG_PATHS:
            self.send_error(404)
            return
        result = response_for(self.path)
        if result.delay_seconds:
            time.sleep(result.delay_seconds)
        data = result.body.encode("utf-8")
        self.send_response(result.status)
        self.send_header("Content-Type", result.content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if result.location:
            self.send_header("Location", result.location)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *_args):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aplicación HTTP controlada de BLACKBOX Local Testing Lab."
    )
    parser.add_argument("--port", type=int, default=3000)
    options = parser.parse_args(argv)
    if not 1024 <= options.port <= 65535:
        parser.error("El puerto debe estar entre 1024 y 65535.")
    server = ThreadingHTTPServer(("127.0.0.1", options.port), LabHandler)
    server.daemon_threads = True
    print(
        f"Aplicación controlada disponible en http://127.0.0.1:{options.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
