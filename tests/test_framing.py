import unittest
from src.http_request import HTTPError, parse_request
from tests.support import RunningServer, request_bytes


class FramingTests(unittest.TestCase):
    def test_ambiguous_lengths_are_rejected(self):
        for headers in ("Content-Length: -1", "Content-Length: 1,1",
                        "Content-Length: 1\r\nContent-Length: 1",
                        "Content-Length: 0\r\nTransfer-Encoding: chunked"):
            with self.subTest(headers=headers), self.assertRaises(HTTPError):
                parse_request(f"POST / HTTP/1.1\r\nHost: local\r\n{headers}\r\n\r\n")

    def test_conflict_closes_before_a_pipelined_request(self):
        with RunningServer() as server:
            request = request_bytes(method="POST", headers="Content-Length: 0\r\nTransfer-Encoding: chunked\r\n")
            response = server.exchange(request + request_bytes())
            self.assertTrue(response.startswith(b"HTTP/1.1 400"))
            self.assertEqual(response.count(b"HTTP/1.1"), 1)
