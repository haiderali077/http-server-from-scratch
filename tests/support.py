import socket
import os
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RunningServer:
    def __init__(self, *options):
        mode = os.environ.get("HTTP_TEST_MODE")
        self.options = (*options, "--mode", mode) if mode and "--mode" not in options else options

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / "index.html").write_bytes(b"hello")
        (self.root / "large.png").write_bytes(b"0123456789abcdef" * 65536)
        self.process = subprocess.Popen(
            [sys.executable, "-u", str(PROJECT_ROOT / "src/webserver.py"), "-p", "0",
             "-d", str(self.root), *self.options],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        if not select.select([self.process.stdout], [], [], 3)[0]:
            self.__exit__(None, None, None)
            raise RuntimeError("Server did not announce its ephemeral port")
        line = self.process.stdout.readline()
        try:
            self.port = int(line.split()[-1])
        except (ValueError, IndexError):
            self.__exit__(None, None, None)
            raise RuntimeError("Server failed before listening")
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
        self.process.stdout.close()


def request_bytes(path="/", method="GET", headers="", body=b""):
    return (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
            f"{headers}\r\n").encode("ascii") + body
