import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tests.support import RunningServer, request_bytes
from src.proxy import Proxy


class Backend(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen = []

    def do_GET(self):
        self.server.seen.append((self.command, self.path, dict(self.headers), b""))
        body = b"backend\n"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Upstream:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        self.server.seen = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ProxyTests(unittest.TestCase):
    def test_local_and_backend_routes(self):
        with Upstream() as backend, RunningServer("--upstream", backend.url) as server:
            self.assertTrue(server.exchange(request_bytes("/static/")).endswith(b"hello"))
            self.assertTrue(server.exchange(request_bytes("/api/example")).endswith(b"backend\n"))
            self.assertEqual(backend.server.seen[0][1], "/example")

    def test_only_configured_origins(self):
        for url in ["https://host", "http://user@host", "http://host/path", "http://host?x=1"]:
            with self.assertRaises(ValueError):
                Proxy(url)
