"""Round-robin over configured origins with bounded lazy health probes."""
import socket
import threading
import time

if __package__:
    from .proxy import Proxy, ProxyFailure, response_header
    from .transport import SocketReader
else:
    from proxy import Proxy, ProxyFailure, response_header
    from transport import SocketReader


class Backends:
    def __init__(self, urls, **options):
        if not 1 <= len(urls) <= 8 or len(set(urls)) != len(urls):
            raise ValueError("Configure one to eight distinct backend origins")
        self.backends = [Proxy(url, **options) for url in urls]
        self.healthy = [False] * len(urls)
        self.lock = threading.Lock()
        self.next_probe = 0.0
        self.cursor = 0
        self.interval = 1.0
        self.probe_timeout = min(.2, self.backends[0].connect_timeout, self.backends[0].response_timeout)

    def probe(self, backend):
        try:
            with socket.create_connection((backend.host, backend.port), timeout=self.probe_timeout) as connection:
                connection.sendall(f"GET /health HTTP/1.1\r\nHost: {backend.authority}\r\nConnection: close\r\n\r\n".encode("ascii"))
                status, _ = response_header(SocketReader(connection), self.probe_timeout)
                return status == 200
        except (OSError, ValueError):
            return False

    def forward(self, request, peer=None):
        started = time.monotonic()
        with self.lock:
            if started >= self.next_probe:
                self.healthy = [self.probe(backend) for backend in self.backends]
                self.next_probe = time.monotonic() + self.interval
            eligible = [index for index, alive in enumerate(self.healthy) if alive]
            if not eligible:
                failure = ProxyFailure("No healthy backend", 503)
                failure.upstream_seconds = time.monotonic() - started
                raise failure
            index = eligible[self.cursor % len(eligible)]
            self.cursor += 1
        try:
            response = self.backends[index].forward(request, peer)
            response.body.on_failure = lambda: self.mark_failed(index)
            return response._replace(upstream_seconds=time.monotonic() - started)
        except ProxyFailure as error:
            self.mark_failed(index)
            error.upstream_seconds = time.monotonic() - started
            raise

    def mark_failed(self, index):
        with self.lock:
            self.healthy[index] = False

    def close(self):
        for backend in self.backends:
            backend.close()
