"""Bound submitted work as well as worker threads."""
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore


class BoundedPool:
    def __init__(self, workers=8, queue_size=16):
        if workers < 1 or queue_size < 0:
            raise ValueError("Workers must be positive and queue size nonnegative")
        self.slots = BoundedSemaphore(workers + queue_size)
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="http")

    def submit(self, function, *arguments):
        if not self.slots.acquire(blocking=False):
            return False
        try:
            future = self.executor.submit(function, *arguments)
        except Exception:
            self.slots.release()
            raise
        future.add_done_callback(lambda unused: self.slots.release())
        return True

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.executor.shutdown(wait=True)
