import unittest
import concurrent.futures
import http.client
import threading
from tests.test_proxy import Upstream
from tests.support import RunningServer, request_bytes
from tests.upstream_support import RawUpstream


class ProxyFailureTests(unittest.TestCase):
    def test_truncated_body_closes_without_second_response(self):
        with RawUpstream(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nshort") as backend, RunningServer("--upstream", backend.url) as server:
            result = server.exchange(request_bytes("/api/x"))
            self.assertEqual(result.count(b"HTTP/1.1"), 1)
            self.assertTrue(result.endswith(b"short"))
            self.assertIn(b"200 OK", server.exchange(request_bytes("/health")))

    def test_stream_arrives_before_upstream_finishes(self):
        first_received = threading.Event()
        def reply(connection):
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\na")
            if not first_received.wait(2):
                return
            connection.sendall(b"b")
        with RawUpstream(reply) as backend, RunningServer("--upstream", backend.url) as server:
            client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
            client.request("GET", "/api/x", headers={"Connection": "close"})
            response = client.getresponse()
            self.assertEqual(response.read(1), b"a")
            first_received.set()
            self.assertEqual(response.read(), b"b")
            client.close()

    def test_chunked_upload_and_concurrent_requests(self):
        with Upstream() as backend, RunningServer("--upstream", backend.url) as server:
            body = b"3\r\nabc\r\n2\r\n\x00x\r\n0\r\n\r\n"
            response = server.exchange(request_bytes("/api/echo", "POST", "Transfer-Encoding: chunked\r\n", body))
            self.assertTrue(response.endswith(b"abc\x00x"))
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                replies = list(pool.map(lambda _: server.exchange(request_bytes("/api/x")), range(24)))
            self.assertTrue(all(r.endswith(b"backend\n") for r in replies))

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
