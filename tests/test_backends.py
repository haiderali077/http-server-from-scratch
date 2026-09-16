import time
import unittest
from tests.test_proxy import Upstream
from tests.upstream_support import RawUpstream
from tests.support import RunningServer, request_bytes


class BackendTests(unittest.TestCase):
    def test_round_robin(self):
        with Upstream() as first, Upstream() as second, RunningServer("--upstream", first.url, "--upstream", second.url) as server:
            for _ in range(6):
                self.assertTrue(server.exchange(request_bytes("/api/work")).endswith(b"backend\n"))
            self.assertEqual(sum(r[1] == "/work" for r in first.server.seen), 3)
            self.assertEqual(sum(r[1] == "/work" for r in second.server.seen), 3)

    def test_unhealthy_backend_skipped(self):
        with RawUpstream(b"HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\n\r\n") as bad, Upstream() as good, RunningServer("--upstream", bad.url, "--upstream", good.url) as server:
            for _ in range(3):
                self.assertTrue(server.exchange(request_bytes("/api/work")).endswith(b"backend\n"))

    def test_unavailable_and_health_recovery(self):
        from src.backends import Backends
        from src.proxy import ProxyFailure
        from src.http_request import HTTPRequest
        from unittest.mock import patch
        group = Backends(["http://127.0.0.1:1", "http://127.0.0.1:2"])
        request = HTTPRequest("GET", "/", "", "HTTP/1.1", {})
        try:
            with patch.object(group, "probe", return_value=False):
                with self.assertRaises(ProxyFailure) as error:
                    group.forward(request)
                self.assertEqual(error.exception.status, 503)
            group.next_probe = 0
            with patch.object(group, "probe", return_value=True), patch.object(group.backends[0], "forward") as forward:
                from src.http_response import build_response
                from src.proxy import UpstreamBody
                from unittest.mock import Mock
                forward.return_value = build_response(200)._replace(body=UpstreamBody(Mock(), iter([b"recovered"])))
                response = group.forward(request)
                self.assertEqual(b"".join(response.body), b"recovered")
                response.body.close()
        finally:
            group.close()
