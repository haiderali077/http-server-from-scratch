import time
import unittest
from tests.support import RunningServer


class ShutdownTests(unittest.TestCase):
    def test_sigterm_bounds_drain_time_with_idle_client(self):
        with RunningServer("--shutdown-timeout", "0.1") as server, server.connect() as idle:
            start = time.monotonic()
            server.process.terminate()
            server.process.wait(timeout=2)
            self.assertLess(time.monotonic() - start, 2)
            self.assertEqual(server.process.returncode, 0)
