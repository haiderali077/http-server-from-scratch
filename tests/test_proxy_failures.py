import unittest
from tests.support import RunningServer, request_bytes
from tests.upstream_support import RawUpstream


class ProxyFailureTests(unittest.TestCase):
    def test_bad_gateway_for_protocol_failure(self):
        with RawUpstream(b"not HTTP\r\n\r\n") as backend, RunningServer("--upstream", backend.url) as server:
            self.assertIn(b"502 Bad Gateway", server.exchange(request_bytes("/api/x")))
            self.assertIn(b"200 OK", server.exchange(request_bytes("/health")))

    def test_gateway_timeout(self):
        with RawUpstream(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n", .2) as backend, RunningServer("--upstream", backend.url, "--upstream-response-timeout", ".05") as server:
            self.assertIn(b"504 Gateway Timeout", server.exchange(request_bytes("/api/x")))

    def test_disconnect_before_headers(self):
        with RawUpstream(b"") as backend, RunningServer("--upstream", backend.url) as server:
            self.assertIn(b"502 Bad Gateway", server.exchange(request_bytes("/api/x")))
