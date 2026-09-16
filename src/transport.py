"""Buffered socket reads: TCP delivers a stream, not whole HTTP messages."""
import socket
import time

if __package__:
    from .http_request import HTTPError
else:
    from http_request import HTTPError


def send_response(connection, response, suppress_body=False):
    """Transmit complete buffers; a successful send() alone is not sufficient."""
    connection.sendall(response.header_bytes())
    if response.body and not suppress_body:
        connection.sendall(response.body)


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
