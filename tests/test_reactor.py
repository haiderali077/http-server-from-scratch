import http.client
import unittest
from tests.support import RunningServer


class ReactorTests(unittest.TestCase):
    def test_idle_connections_do_not_occupy_workers(self):
        with RunningServer("--mode", "selectors", "--workers", "1") as server:
            clients = []
            try:
                for _ in range(12):
                    client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
                    client.request("GET", "/health")
                    self.assertEqual(client.getresponse().read(), b"ok\n")
                    clients.append(client)
                clients[0].request("GET", "/health")
                self.assertEqual(clients[0].getresponse().read(), b"ok\n")
            finally:
                for client in clients:
                    client.close()
