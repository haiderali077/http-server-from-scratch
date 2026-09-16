import unittest
from tests.support import RunningServer, request_bytes


class FixtureTests(unittest.TestCase):
    def test_ephemeral_port_and_temporary_files(self):
        with RunningServer() as server:
            self.assertGreater(server.port, 0)
            root = server.root
            process = server.process
            self.assertTrue(server.exchange(request_bytes()).endswith(b"hello"))
        self.assertFalse(root.exists())
        self.assertIsNotNone(process.poll())
