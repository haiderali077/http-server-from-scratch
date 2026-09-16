import socket
import unittest
from src.upstream_pool import UpstreamPool
from tests.test_proxy import Upstream
from tests.support import RunningServer, request_bytes
from tests.upstream_support import RawUpstream


class PoolTests(unittest.TestCase):
    def test_exclusive_bounded_leases(self):
        with Upstream() as backend:
            pool = UpstreamPool("127.0.0.1", backend.server.server_port, 1, .05)
            connection = pool.acquire()
            try:
                with self.assertRaises(socket.timeout):
                    pool.acquire()
                self.assertEqual(pool.total, 1)
                pool.release(connection, True)
                self.assertIs(pool.acquire(), connection)
                pool.release(connection, False)
                self.assertEqual(pool.total, 0)
            finally:
                pool.close()

    def test_backend_connection_reuse(self):
        with Upstream() as backend, RunningServer("--upstream", backend.url, "--upstream-pool-size", "2") as server:
            for _ in range(5):
                self.assertTrue(server.exchange(request_bytes("/api/x")).endswith(b"backend\n"))
            self.assertEqual(len(set(r[4] for r in backend.server.seen)), 1)

    def test_closed_upstream_not_reused(self):
        with RawUpstream(b"HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 2\r\n\r\nok") as backend, RunningServer("--upstream", backend.url, "--upstream-pool-size", "1") as server:
            for _ in range(5):
                self.assertTrue(server.exchange(request_bytes("/api/x")).endswith(b"ok"))
