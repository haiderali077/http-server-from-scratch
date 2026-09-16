"""Buffered socket reads: TCP delivers a stream, not whole HTTP messages."""

if __package__:
    from .http_request import HTTPError
else:
    from http_request import HTTPError


class SocketReader:
    def __init__(self, connection):
        self.connection = connection
        self.buffer = bytearray()

    def read_until(self, delimiter, limit=32768, error_status=431):
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
            data = self.connection.recv(4096)
            if not data:
                if self.buffer:
                    raise ValueError("Client disconnected during a message")
                return b""
            self.buffer.extend(data)
