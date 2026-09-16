"""Buffered socket reads: TCP delivers a stream, not whole HTTP messages."""
import socket
import time
import re

if __package__:
    from .http_request import HTTPError
else:
    from http_request import HTTPError


def send_response(connection, response, suppress_body=False):
    """Transmit complete buffers; a successful send() alone is not sufficient."""
    try:
        connection.sendall(response.header_bytes())
        if suppress_body or response.status in (204, 304):
            return
        chunks = [response.body] if isinstance(response.body, bytes) else response.body
        chunked = response.headers.get("Transfer-Encoding") == "chunked"
        sent = 0
        expected = int(response.headers["Content-Length"]) if "Content-Length" in response.headers else None
        for chunk in chunks:
            if chunk:
                sent += len(chunk)
                if expected is not None and sent > expected:
                    raise ValueError("Response exceeds declared length")
                connection.sendall(f"{len(chunk):x}\r\n".encode("ascii") + chunk + b"\r\n" if chunked else chunk)
        if expected is not None and sent != expected:
            raise ValueError("Response shorter than declared length")
        if chunked:
            connection.sendall(b"0\r\n\r\n")
    finally:
        close = getattr(response.body, "close", None)
        if close:
            close()


class BodyStream:
    """Track whether forwarding consumed the complete downstream body."""
    def __init__(self, chunks):
        self.chunks = chunks
        self.complete = False
    def __iter__(self):
        yield from self.chunks
        self.complete = True


class SocketReader:
    def __init__(self, connection):
        self.connection = connection
        self.buffer = bytearray()

    def read_until(self, delimiter, limit=32768, error_status=431, timeout=None):
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            position = self.buffer.find(delimiter)
            if position >= 0:
                end = position + len(delimiter)
                if end > limit:
                    raise HTTPError("Message section exceeds configured limit", error_status)
                result = bytes(self.buffer[:end])
                del self.buffer[:end]
                return result
            if len(self.buffer) >= limit:
                raise HTTPError("Message section exceeds configured limit", error_status)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout("Message read deadline exceeded")
                self.connection.settimeout(remaining)
            data = self.connection.recv(4096)
            if not data:
                if self.buffer:
                    raise ValueError("Client disconnected during a message")
                return b""
            self.buffer.extend(data)

    def read_exact(self, size, limit=1048576, timeout=10.0):
        if size < 0 or size > limit:
            raise HTTPError("Body exceeds configured limit", 413)
        deadline = time.monotonic() + timeout
        while len(self.buffer) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("Body read deadline exceeded")
            self.connection.settimeout(remaining)
            data = self.connection.recv(min(65536, size - len(self.buffer)))
            if not data:
                raise HTTPError("Incomplete request body")
            self.buffer.extend(data)
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def iter_exact(self, size, limit=1048576, timeout=10.0):
        if not 0 <= size <= limit:
            raise HTTPError("Body exceeds configured limit", 413)
        deadline = time.monotonic() + timeout
        while size:
            amount = min(size, 16384)
            yield self.read_exact(amount, limit, max(0, deadline - time.monotonic()))
            size -= amount

    def iter_chunked(self, limit=1048576, timeout=10.0):
        deadline = time.monotonic() + timeout
        total = 0
        while True:
            line = self.read_until(b"\r\n", 128, 400, max(0, deadline - time.monotonic()))
            text = line[:-2].partition(b";")[0]
            if not re.fullmatch(rb"[0-9A-Fa-f]{1,16}", text):
                raise HTTPError("Invalid chunk size")
            size = int(text, 16)
            total += size
            if total > limit:
                raise HTTPError("Decoded body exceeds configured limit", 413)
            if not size:
                if self.read_until(b"\r\n", 32768, 400, max(0, deadline - time.monotonic())) != b"\r\n":
                    raise HTTPError("Trailers are unsupported")
                return
            yield from self.iter_exact(size, limit, max(0, deadline - time.monotonic()))
            if self.read_exact(2, 2, max(0, deadline - time.monotonic())) != b"\r\n":
                raise HTTPError("Missing chunk terminator")

    def read_chunked(self, limit=1048576, timeout=10.0):
        deadline = time.monotonic() + timeout
        body = bytearray()
        while True:
            line = self.read_until(b"\r\n", 128, 400, max(0, deadline - time.monotonic()))
            size_text = line[:-2].partition(b";")[0]
            if not re.fullmatch(rb"[0-9A-Fa-f]{1,16}", size_text):
                raise HTTPError("Invalid chunk size")
            size = int(size_text, 16)
            if size > limit - len(body):
                raise HTTPError("Decoded body exceeds configured limit", 413)
            if not size:
                if self.read_until(b"\r\n", 32768, 400, max(0, deadline - time.monotonic())) != b"\r\n":
                    raise HTTPError("Request trailers are not supported")
                return bytes(body)
            body.extend(self.read_exact(size, limit, max(0, deadline - time.monotonic())))
            if self.read_exact(2, 2, max(0, deadline - time.monotonic())) != b"\r\n":
                raise HTTPError("Missing chunk terminator")
