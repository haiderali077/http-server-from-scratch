"""A configured HTTP upstream reached through raw TCP sockets."""
import socket
from urllib.parse import quote, urlsplit

if __package__:
    from .http_response import build_response
    from .transport import SocketReader
else:
    from http_response import build_response
    from transport import SocketReader


class Proxy:
    def __init__(self, url):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.username or
                parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Upstream must be an http://host:port origin without credentials or path")
        self.host, self.port = parsed.hostname, parsed.port or 80
        self.authority = f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"

    def forward(self, request):
        path = quote(request.path, safe="/!$&'()*+,;=:@-._~")
        with socket.create_connection((self.host, self.port), timeout=5) as connection:
            connection.sendall(f"GET {path} HTTP/1.1\r\nHost: {self.authority}\r\nConnection: close\r\n\r\n".encode("ascii"))
            reader = SocketReader(connection)
            header = reader.read_until(b"\r\n\r\n", timeout=5).decode("iso-8859-1")
            lines = header.split("\r\n")
            status = int(lines[0].split(" ")[1])
            headers = dict(line.split(":", 1) for line in lines[1:] if line)
            length = int(headers.get("Content-Length", "0"))
            body = reader.read_exact(length, 64 * 1024 * 1024, 10)
            return build_response(status, body, {"Content-Type": headers.get("Content-Type", "application/octet-stream").strip()})
