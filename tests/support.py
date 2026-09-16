import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RunningServer:
    def __init__(self, *options):
        self.options = options

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "index.html").write_bytes(b"hello")
        (self.root / "large.png").write_bytes(b"0123456789abcdef" * 65536)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.process = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "src/webserver.py"), "-p", str(self.port),
             "-d", str(self.root), *self.options],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                self.connect().close()
                return self
            except OSError:
                time.sleep(0.02)
        self.__exit__(None, None, None)
        raise RuntimeError("Server failed to start")

    def connect(self):
        return socket.create_connection(("127.0.0.1", self.port), timeout=3)

    def exchange(self, request):
        with self.connect() as connection:
            connection.sendall(request)
            result = bytearray()
            while True:
                data = connection.recv(65536)
                if not data:
                    return bytes(result)
                result.extend(data)

    def __exit__(self, *unused):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.directory.cleanup()


def request_bytes(path="/", method="GET", headers="", body=b""):
    return (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
            f"{headers}\r\n").encode("ascii") + body
