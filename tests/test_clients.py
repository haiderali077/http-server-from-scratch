from concurrent.futures import ThreadPoolExecutor
import http.client
import time
import unittest
from tests.support import RunningServer, request_bytes


class ClientTests(unittest.TestCase):
    def test_simultaneous_clients(self):
        with RunningServer() as server, ThreadPoolExecutor(max_workers=12) as clients:
            results = list(clients.map(lambda unused: server.exchange(request_bytes("/health")), range(24)))
            self.assertTrue(all(result.startswith(b"HTTP/1.1 200") for result in results))

    def test_partial_body_times_out(self):
        with RunningServer("--body-timeout", "0.05") as server:
            wire = server.exchange(request_bytes("/echo", "POST", "Content-Length: 5\r\n", b"ab"))
            self.assertTrue(wire.startswith(b"HTTP/1.1 408"))
            self.assertTrue(server.exchange(request_bytes()).startswith(b"HTTP/1.1 200"))

    def test_idle_connection_closes_and_fresh_request_recovers(self):
        with RunningServer("--idle-timeout", "0.05") as server:
            client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=2)
            try:
                client.request("GET", "/health")
                self.assertEqual(client.getresponse().read(), b"ok\n")
                time.sleep(0.1)
                self.assertEqual(client.sock.recv(1), b"")
            finally:
                client.close()
            self.assertTrue(server.exchange(request_bytes()).startswith(b"HTTP/1.1 200"))
