import http.client
import unittest
from tests.support import RunningServer
from tests.support import request_bytes


class PersistenceTests(unittest.TestCase):
    def test_pipelined_requests_preserve_bytes_and_response_order(self):
        with RunningServer() as server:
            (server.root / "second.html").write_bytes(b"second response")
            first = b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n"
            wire = server.exchange(first + request_bytes("/second.html"))
            self.assertEqual(wire.count(b"HTTP/1.1 200 OK"), 2)
            self.assertLess(wire.index(b"hello"), wire.index(b"second response"))
            self.assertTrue(wire.endswith(b"second response"))

    def test_two_requests_reuse_one_socket(self):
        with RunningServer() as server:
            client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
            try:
                client.request("GET", "/")
                first = client.getresponse()
                self.assertEqual(first.read(), b"hello")
                self.assertEqual(first.getheader("Connection"), "keep-alive")
                first_socket = client.sock
                client.request("GET", "/", headers={"Connection": "close"})
                second = client.getresponse()
                self.assertEqual(second.read(), b"hello")
                self.assertEqual(second.getheader("Connection"), "close")
                self.assertIsNotNone(first_socket)
            finally:
                client.close()
