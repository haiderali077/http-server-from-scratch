import threading
import unittest
from src.workers import BoundedPool
from tests.support import RunningServer, request_bytes


class WorkerTests(unittest.TestCase):
    def test_queue_and_active_work_are_bounded(self):
        release = threading.Event()
        entered = threading.Event()

        def wait():
            entered.set()
            release.wait(2)

        with BoundedPool(1, 1) as pool:
            try:
                self.assertTrue(pool.submit(wait))
                self.assertTrue(entered.wait(1))
                self.assertTrue(pool.submit(wait))
                self.assertFalse(pool.submit(wait))
            finally:
                release.set()

    def test_idle_client_does_not_block_other_clients(self):
        with RunningServer() as server, server.connect() as idle:
            result = server.exchange(request_bytes())
            self.assertTrue(result.startswith(b"HTTP/1.1 200"))
