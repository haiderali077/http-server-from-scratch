import http.client
import unittest
from tests.support import RunningServer


class PersistenceTests(unittest.TestCase):
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
