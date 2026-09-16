import unittest
import http.client
from tests.support import RunningServer, request_bytes


class WireTests(unittest.TestCase):
    def test_head_has_get_length_but_no_body(self):
        with RunningServer() as server:
            client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
            try:
                client.request("HEAD", "/large.png", headers={"Connection": "close"})
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Length"), "1048576")
                self.assertEqual(response.read(), b"")
            finally:
                client.close()

    def test_large_response_is_complete(self):
        with RunningServer() as server:
            head, body = server.exchange(request_bytes("/large.png")).split(b"\r\n\r\n", 1)
            self.assertIn(b"Content-Length: 1048576", head)
            self.assertEqual(body, (server.root / "large.png").read_bytes())

    def test_query_and_encoded_filename_over_tcp(self):
        with RunningServer() as server:
            (server.root / "café.html").write_bytes(b"unicode filename")
            result = server.exchange(request_bytes("/caf%C3%A9.html?download=1"))
            self.assertTrue(result.startswith(b"HTTP/1.1 200"))
            self.assertTrue(result.endswith(b"unicode filename"))

    def test_malformed_request_does_not_stop_server(self):
        with RunningServer() as server:
            self.assertTrue(server.exchange(b"GET / HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 400"))
            self.assertTrue(server.exchange(request_bytes()).startswith(b"HTTP/1.1 200"))

    def test_traversal_is_forbidden_over_tcp(self):
        with RunningServer() as server:
            self.assertTrue(server.exchange(request_bytes("/%2e%2e/private.html")).startswith(b"HTTP/1.1 403"))
