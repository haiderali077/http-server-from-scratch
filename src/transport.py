"""Buffered socket reads: TCP delivers a stream, not whole HTTP messages."""


class SocketReader:
    def __init__(self, connection):
        self.connection = connection
        self.buffer = bytearray()

    def read_until(self, delimiter):
        while True:
            position = self.buffer.find(delimiter)
            if position >= 0:
                end = position + len(delimiter)
                result = bytes(self.buffer[:end])
                del self.buffer[:end]
                return result
            data = self.connection.recv(4096)
            if not data:
                if self.buffer:
                    raise ValueError("Client disconnected during a message")
                return b""
            self.buffer.extend(data)
