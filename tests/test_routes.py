import http.client
import unittest
from tests.support import RunningServer


class RouteTests(unittest.TestCase):
    def test_echo_accepts_fixed_and_chunked_binary_bodies(self):
        with RunningServer() as server:
            client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
            try:
                for body, chunked in ((b"binary\x00\xff", False), (iter([b"first", b"second"]), True)):
                    client.request("POST", "/echo", body=body, encode_chunked=chunked)
                    response = client.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), b"firstsecond" if chunked else b"binary\x00\xff")
            finally:
                client.close()
