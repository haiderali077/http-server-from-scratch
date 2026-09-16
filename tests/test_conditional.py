import os
import unittest
from src.http_response import format_http_date
from src.static_files import is_not_modified
from tests.support import RunningServer, request_bytes


class ConditionalTests(unittest.TestCase):
    def test_http_second_precision(self):
        timestamp = 1700000000.987
        self.assertTrue(is_not_modified(timestamp, format_http_date(timestamp)))
        self.assertFalse(is_not_modified(timestamp, format_http_date(timestamp - 1)))
        self.assertFalse(is_not_modified(timestamp, "bad date"))

    def test_reusing_last_modified_returns_304(self):
        with RunningServer() as server:
            path = server.root / "index.html"
            os.utime(path, (1700000000.987, 1700000000.987))
            response = server.exchange(request_bytes())
            modified = next(line.partition(b": ")[2] for line in response.split(b"\r\n") if line.startswith(b"Last-Modified:"))
            result = server.exchange(request_bytes(headers="If-Modified-Since: " + modified.decode() + "\r\n"))
            self.assertIn(b"304 Not Modified", result)
            self.assertTrue(result.endswith(b"\r\n\r\n"))
