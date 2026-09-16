import gzip
import unittest
from src.encoding import qualities
from tests.support import RunningServer, request_bytes


class GzipTests(unittest.TestCase):
    def test_variant_lengths_head_and_validators(self):
        with RunningServer() as server:
            def fields(result):
                header, body = result.split(b"\r\n\r\n", 1)
                return {name.lower(): value for name, _, value in (line.partition(b": ") for line in header.split(b"\r\n")[1:])}, body
            plain, plain_body = fields(server.exchange(request_bytes()))
            compressed, compressed_body = fields(server.exchange(request_bytes(headers="Accept-Encoding: gzip\r\n")))
            self.assertNotEqual(plain[b"etag"], compressed[b"etag"])
            self.assertEqual(int(compressed[b"content-length"]), len(compressed_body))
            head, body = fields(server.exchange(request_bytes(method="HEAD", headers="Accept-Encoding: gzip\r\n")))
            self.assertEqual(head[b"content-length"], compressed[b"content-length"])
            self.assertEqual(body, b"")
            condition = "If-None-Match: " + compressed[b"etag"].decode() + "\r\n"
            result = server.exchange(request_bytes(headers="Accept-Encoding: gzip\r\n" + condition))
            self.assertIn(b"304 Not Modified", result)
            self.assertIn(b"Vary: Accept-Encoding", result)
            self.assertTrue(result.endswith(b"\r\n\r\n"))
            self.assertIn(b"200 OK", server.exchange(request_bytes(headers=condition)))
    def test_quality_values(self):
        self.assertEqual(qualities(None), (0, 1))
        self.assertEqual(qualities("gzip;q=0, identity;q=1"), (0, 1))
        self.assertEqual(qualities("*;q=0"), (0, 0))
        self.assertEqual(qualities("gzip;q=1.5"), (0, 1))

    def test_negotiated_bytes_and_exclusion(self):
        with RunningServer() as server:
            result = server.exchange(request_bytes(headers="Accept-Encoding: gzip\r\n"))
            headers, body = result.split(b"\r\n\r\n", 1)
            self.assertIn(b"Content-Encoding: gzip", headers)
            self.assertIn(b"Vary: Accept-Encoding", headers)
            self.assertEqual(gzip.decompress(body), b"hello")
            plain = server.exchange(request_bytes(headers="Accept-Encoding: gzip;q=0\r\n"))
            self.assertNotIn(b"Content-Encoding:", plain)
            self.assertTrue(plain.endswith(b"hello"))
            self.assertIn(b"406 Not Acceptable", server.exchange(request_bytes(headers="Accept-Encoding: *;q=0\r\n")))
