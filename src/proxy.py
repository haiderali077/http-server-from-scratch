"""A configured HTTP upstream reached through raw TCP sockets."""
import socket
import re
import time
from urllib.parse import quote, urlsplit

if __package__:
    from .http_response import build_response
    from .transport import BodyStream, SocketReader
    from .http_request import HTTPError, TOKEN
else:
    from http_response import build_response
    from transport import BodyStream, SocketReader
    from http_request import HTTPError, TOKEN


HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"}


def end_to_end_headers(headers):
    """Each Connection token names an additional field local to this hop."""
    lower = {name.lower(): value if isinstance(value, list) else value.strip() for name, value in headers.items()}
    excluded = HOP_HEADERS | {part.strip().lower() for part in lower.get("connection", "").split(",")}
    return {name: value for name, value in lower.items() if name not in excluded}


def response_header(reader, timeout=5):
    """Strict response framing before any bytes are committed downstream."""
    deadline = time.monotonic() + timeout
    for _ in range(9):
        raw = reader.read_until(b"\r\n\r\n", timeout=max(0, deadline - time.monotonic()))
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
    return b"".join(response_chunks(reader, request, status, headers))


def response_chunks(reader, request, status, headers, timeout=10):
    if request.method == "HEAD" or status in (204, 304):
        return
    if "transfer-encoding" in headers:
        yield from reader.iter_chunked(64 * 1024 * 1024, timeout)
        return
    if "content-length" in headers:
        yield from reader.iter_exact(int(headers["content-length"]), 64 * 1024 * 1024, timeout)
        return
    import time
    deadline = time.monotonic() + timeout
    total = len(reader.buffer)
    if reader.buffer:
        yield bytes(reader.buffer)
    reader.buffer.clear()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("Upstream body deadline exceeded")
        reader.connection.settimeout(remaining)
        data = reader.connection.recv(16384)
        if not data:
            return
        total += len(data)
        if total > 64 * 1024 * 1024:
            raise ValueError("Upstream body exceeds limit")
        yield data


class UpstreamBody:
    def __init__(self, connection, chunks):
        self.connection, self.chunks = connection, chunks
    def __iter__(self):
        yield from self.chunks
    def close(self):
        self.connection.close()


class ProxyFailure(HTTPError):
    pass


class Proxy:
    def __init__(self, url, connect_timeout=2.0, response_timeout=10.0):
        if min(connect_timeout, response_timeout) <= 0:
            raise ValueError("Upstream timeouts must be positive")
        self.connect_timeout, self.response_timeout = connect_timeout, response_timeout
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or not parsed.hostname or parsed.username or
                parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("Upstream must be an http://host:port origin without credentials or path")
        self.host, self.port = parsed.hostname, parsed.port or 80
        self.authority = f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"

    def forward(self, request, peer=None):
        try:
            return self._forward(request, peer)
        except socket.timeout as error:
            raise ProxyFailure("Upstream timed out", 504) from error
        except (OSError, ValueError) as error:
            if isinstance(error, HTTPError):
                raise
            raise ProxyFailure("Upstream connection or protocol failure", 502) from error

    def _forward(self, request, peer=None):
        path = quote(request.path, safe="/!$&'()*+,;=:@-._~")
        if request.query:
            path += "?" + request.query
        connection = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
        try:
            connection.settimeout(self.response_timeout)
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
            fields.update({"Host": self.authority, "Connection": "close"})
            chunked = "transfer-encoding" in request.headers
            fields["Transfer-Encoding" if chunked else "Content-Length"] = "chunked" if chunked else request.headers.get("content-length", str(len(request.body)) if isinstance(request.body, bytes) else "0")
            message = f"{request.method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in fields.items()) + "\r\n"
            connection.sendall(message.encode("iso-8859-1"))
            chunks = [request.body] if isinstance(request.body, bytes) else request.body
            for chunk in chunks:
                if chunk:
                    connection.sendall(f"{len(chunk):x}\r\n".encode("ascii") + chunk + b"\r\n" if chunked else chunk)
            if chunked:
                connection.sendall(b"0\r\n\r\n")
            reader = SocketReader(connection)
            try:
                status, headers = response_header(reader, self.response_timeout)
            except HTTPError as error:
                raise ProxyFailure("Upstream header protocol failure", 502) from error
            forwarded = {name.title(): value for name, value in end_to_end_headers(headers).items() if name not in {"content-length", "server", "date"}}
            response = build_response(status, headers=forwarded)
            if "content-length" in headers and status != 204 and status != 304:
                response.headers["Content-Length"] = headers["content-length"]
            elif request.method != "HEAD" and status not in (204, 304):
                response.headers.pop("Content-Length", None)
                response.headers["Transfer-Encoding"] = "chunked"
            body = UpstreamBody(connection, response_chunks(reader, request, status, headers, self.response_timeout))
            return response._replace(body=body)
        except BaseException:
            connection.close()
            raise
