"""Exclusive, bounded upstream socket leases with no automatic request retry."""
import select
import socket
import threading
import time


class UpstreamPool:
    def __init__(self, host, port, size, timeout):
        if size < 1:
            raise ValueError("Upstream pool size must be positive")
        self.host, self.port, self.size, self.timeout = host, port, size, timeout
        self.condition = threading.Condition()
        self.idle = []
        self.total = 0
        self.closed = False

    def acquire(self):
        deadline = time.monotonic() + self.timeout
        with self.condition:
            while True:
                if self.closed:
                    raise OSError("Upstream pool closed")
                if self.idle:
                    connection = self.idle.pop()
                    if select.select([connection], [], [], 0)[0]:
                        connection.close()
                        self.total -= 1
                        continue
                    return connection
                if self.total < self.size:
                    self.total += 1
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout("Upstream pool lease timed out")
                self.condition.wait(remaining)
        try:
            return socket.create_connection((self.host, self.port), timeout=max(.001, deadline - time.monotonic()))
        except BaseException:
            with self.condition:
                self.total -= 1
                self.condition.notify()
            raise

    def release(self, connection, reusable):
        with self.condition:
            if reusable and not self.closed:
                self.idle.append(connection)
            else:
                connection.close()
                self.total -= 1
            self.condition.notify()

    def close(self):
        with self.condition:
            self.closed = True
            for connection in self.idle:
                connection.close()
                self.total -= 1
            self.idle.clear()
            self.condition.notify_all()
