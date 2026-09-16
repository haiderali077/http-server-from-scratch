import http.client
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import unittest
from tests.support import RunningServer
from tests.test_proxy import Upstream


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL CLI required to generate temporary test certificate")
class TLSTests(unittest.TestCase):
    def test_verified_https_proxy_and_handshake_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            cert, key = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                            "-keyout", str(key), "-out", str(cert)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with Upstream() as backend, RunningServer("--mode", "threads", "--tls-cert", str(cert), "--tls-key", str(key),
                                                     "--tls-handshake-timeout", ".15", "--upstream", backend.url) as server:
                context = ssl.create_default_context(cafile=str(cert))
                context.set_alpn_protocols(["http/1.1"])
                client = http.client.HTTPSConnection("localhost", server.port, context=context, timeout=3)
                try:
                    client.request("GET", "/health")
                    self.assertEqual(client.getresponse().read(), b"ok\n")
                    self.assertEqual(client.sock.selected_alpn_protocol(), "http/1.1")
                    client.request("GET", "/api/item")
                    self.assertEqual(client.getresponse().read(), b"backend\n")
                    fields = {k.lower(): v for k, v in backend.server.seen[-1][2].items()}
                    self.assertEqual(fields["x-forwarded-proto"], "https")
                finally:
                    client.close()
                with socket.create_connection(("127.0.0.1", server.port), timeout=3) as stalled:
                    self.assertEqual(stalled.recv(1), b"")
                untrusted = http.client.HTTPSConnection("localhost", server.port, timeout=3)
                try:
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        untrusted.request("GET", "/health")
                finally:
                    untrusted.close()
