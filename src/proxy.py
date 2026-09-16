"""A configured HTTP upstream reached through raw TCP sockets."""
import socket
import re
from urllib.parse import quote, urlsplit

if __package__:
    from .http_response import build_response
    from .transport import SocketReader
    from .http_request import TOKEN
else:
    from http_response import build_response
    from transport import SocketReader
    from http_request import TOKEN


HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}


def end_to_end_headers(headers):
    """Each Connection token names an additional field local to this hop."""
    lower = {name.lower(): value if isinstance(value, list) else value.strip() for name, value in headers.items()}
    excluded = HOP_HEADERS | {part.strip().lower() for part in lower.get("connection", "").split(",")}
    return {name: value for name, value in lower.items() if name not in excluded}


def response_header(reader, timeout=5):
    """Strict response framing before any bytes are committed downstream."""
    for _ in range(9):
        raw = reader.read_until(b"\r\n\r\n", timeout=timeout)
        lines = raw.decode("iso-8859-1").split("\r\n")
        match = re.fullmatch(r"HTTP/1\.[01] ([1-5][0-9]{2})(?: [^\r\n]*)?", lines[0])
        if not match:
            raise ValueError("Invalid upstream status line")
        status = int(match[1])
        headers = {}
        for line in lines[1:]:
            if not line:
                continue
            name, colon, value = line.partition(":")
            if not colon or not TOKEN.fullmatch(name) or any(ord(c) < 32 and c != "\t" or ord(c) == 127 for c in value):
                raise ValueError("Invalid upstream header")
            name, value = name.lower(), value.strip()
            if name in headers:
                if name in {"content-length", "transfer-encoding"}:
                    raise ValueError("Duplicate upstream framing")
                if name == "set-cookie":
                    if not isinstance(headers[name], list):
                        headers[name] = [headers[name]]
                    headers[name].append(value)
                else:
                    headers[name] += ", " + value
            else:
                headers[name] = value
        length = headers.get("content-length")
        encoding = headers.get("transfer-encoding")
        if length is not None and (not re.fullmatch(r"[0-9]{1,12}", length) or int(length) > 64 * 1024 * 1024):
            raise ValueError("Invalid or excessive upstream Content-Length")
        if encoding and (length is not None or encoding.lower() != "chunked"):
            raise ValueError("Conflicting or unsupported upstream framing")
        if status == 101:
            raise ValueError("Protocol upgrade is unsupported")
        if status >= 200:
            return status, headers
    raise ValueError("Too many informational responses")


def response_body(reader, request, status, headers):
    if request.method == "HEAD" or status in (204, 304):
        return b""
    if "transfer-encoding" in headers:
        return reader.read_chunked(64 * 1024 * 1024, 10)
    if "content-length" in headers:
        return reader.read_exact(int(headers["content-length"]), 64 * 1024 * 1024, 10)
    body = bytearray(reader.buffer)
    reader.buffer.clear()
    while True:
        data = reader.connection.recv(65536)
        if not data:
            return bytes(body)
        body.extend(data)
        if len(body) > 64 * 1024 * 1024:
            raise ValueError("Upstream body exceeds limit")


class Proxy:
    def __init__(self, url):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.username or
                parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Upstream must be an http://host:port origin without credentials or path")
        self.host, self.port = parsed.hostname, parsed.port or 80
        self.authority = f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"

    def forward(self, request, peer=None):
        path = quote(request.path, safe="/!$&'()*+,;=:@-._~")
        if request.query:
            path += "?" + request.query
        with socket.create_connection((self.host, self.port), timeout=5) as connection:
            fields = end_to_end_headers(request.headers)
            fields.pop("host", None)
            fields.pop("content-length", None)
            for name in list(fields):
                if name == "forwarded" or name.startswith("x-forwarded-"):
                    del fields[name]
            fields["X-Forwarded-Host"] = request.headers.get("host", "")
            fields["X-Forwarded-Proto"] = "http"
            if peer:
                fields["X-Forwarded-For"] = peer[0]
            fields.update({"Host": self.authority, "Connection": "close", "Content-Length": str(len(request.body))})
            message = f"{request.method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in fields.items()) + "\r\n"
            connection.sendall(message.encode("iso-8859-1"))
            if request.body:
                connection.sendall(request.body)
            reader = SocketReader(connection)
            status, headers = response_header(reader)
            body = response_body(reader, request, status, headers)
            forwarded = {name.title(): value for name, value in end_to_end_headers(headers).items() if name not in {"content-length", "server", "date"}}
            response = build_response(status, body, forwarded)
            if request.method == "HEAD" and "content-length" in headers:
                response.headers["Content-Length"] = headers["content-length"]
            return response
