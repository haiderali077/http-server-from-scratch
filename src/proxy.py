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
        if request.query:
            path += "?" + request.query
        with socket.create_connection((self.host, self.port), timeout=5) as connection:
            fields = {"Host": self.authority, "Connection": "close", "Content-Length": str(len(request.body))}
            if "content-type" in request.headers:
                fields["Content-Type"] = request.headers["content-type"]
            message = f"{request.method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in fields.items()) + "\r\n"
            connection.sendall(message.encode("iso-8859-1"))
            if request.body:
                connection.sendall(request.body)
            reader = SocketReader(connection)
            header = reader.read_until(b"\r\n\r\n", timeout=5).decode("iso-8859-1")
            lines = header.split("\r\n")
            status = int(lines[0].split(" ")[1])
            headers = dict(line.split(":", 1) for line in lines[1:] if line)
            length = int(headers.get("Content-Length", "0"))
            body = b"" if request.method == "HEAD" else reader.read_exact(length, 64 * 1024 * 1024, 10)
            response = build_response(status, body, {"Content-Type": headers.get("Content-Type", "application/octet-stream").strip()})
            if request.method == "HEAD":
                response.headers["Content-Length"] = str(length)
            return response
