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

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.seen.append((self.command, self.path, dict(self.headers), body))
        self.send_response(201)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "8")
        self.end_headers()


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

    def test_prefix_boundaries(self):
        with Upstream() as backend, RunningServer("--upstream", backend.url) as server:
            for path in ("/api", "/api/", "/api/a%20b"):
                self.assertIn(b"200 OK", server.exchange(request_bytes(path)))
            self.assertEqual([r[1] for r in backend.server.seen], ["/", "/", "/a%20b"])
            self.assertIn(b"404 Not Found", server.exchange(request_bytes("/apiculture")))

    def test_methods_queries_and_binary_bodies(self):
        with Upstream() as backend, RunningServer("--upstream", backend.url) as server:
            result = server.exchange(request_bytes("/api/echo?q=a%20b&x=1", "POST", "Content-Length: 3\r\n", b"\x00\xffx"))
            self.assertIn(b"201 Created", result)
            self.assertTrue(result.endswith(b"\x00\xffx"))
            self.assertEqual(backend.server.seen[-1][1], "/echo?q=a%20b&x=1")
            head = server.exchange(request_bytes("/api/item", "HEAD"))
            self.assertTrue(head.endswith(b"\r\n\r\n"))
            self.assertIn(b"Content-Length: 8", head)
