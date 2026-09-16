import http.client
import unittest
from tests.support import RunningServer


class MatrixTests(unittest.TestCase):
    def test_status_methods_binary_and_cache_matrix(self):
        with RunningServer() as server:
            client = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
            try:
                for method, path, status in (("GET", "/", 200), ("HEAD", "/", 200),
                                             ("GET", "/missing.html", 404), ("PUT", "/", 405),
                                             ("GET", "/../secret.html", 403), ("GET", "/no.txt", 415)):
                    with self.subTest(method=method, path=path):
                        client.request(method, path)
                        response = client.getresponse()
                        self.assertEqual(response.status, status)
                        response.read()
                client.request("GET", "/", headers={"If-Modified-Since": "Tue, 01 Jan 2030 00:00:00 GMT"})
                response = client.getresponse()
                self.assertEqual(response.status, 304)
                self.assertEqual(response.read(), b"")
                client.request("GET", "/large.png")
                response = client.getresponse()
                self.assertEqual(response.getheader("Content-Type"), "image/png")
                self.assertEqual(response.read(), (server.root / "large.png").read_bytes())
            finally:
                client.close()
