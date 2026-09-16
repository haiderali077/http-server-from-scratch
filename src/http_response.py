"""Construct HTTP response data and serialize it independently of transport."""

from datetime import datetime, timezone
from http import HTTPStatus
from typing import Dict, NamedTuple


SERVER_NAME = "SimplePythonServer/1.0"


def format_http_date(timestamp=None):
    if timestamp is None:
        date = datetime.now(timezone.utc)
    else:
        date = datetime.fromtimestamp(timestamp, timezone.utc)
    return date.strftime("%a, %d %b %Y %H:%M:%S GMT")


class HTTPResponse(NamedTuple):
    status: int
    headers: Dict[str, str]
    body: bytes
    upstream_seconds: float | None = None

    def header_bytes(self):
        """Serialize the status line and headers, ending with a blank line."""
        try:
            reason = HTTPStatus(self.status).phrase
        except ValueError:
            reason = "Unknown"
        lines = ["HTTP/1.1 {} {}".format(self.status, reason)]
        for name, value in self.headers.items():
            for item in value if isinstance(value, list) else [value]:
                lines.append("{}: {}".format(name, item))
        return ("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1")


def build_response(status, body=b"", headers=None):
    """Add the common headers in one place; bodies are already encoded bytes."""
    response_headers = {
        "Date": format_http_date(),
        "Server": SERVER_NAME,
    }
    if headers:
        response_headers.update(headers)

    if status in (204, 304) or 100 <= status < 200:
        # The existing conditional GET response has no body or Content-Length.
        body = b""
        response_headers.pop("Content-Length", None)
    else:
        response_headers["Content-Length"] = str(len(body))
    response_headers["Connection"] = "close"
    return HTTPResponse(status, response_headers, body)


def error_response(status, headers=None):
    """Build the same HTML error page for every supported error status."""
    reason = HTTPStatus(status).phrase
    body = "<html><body><h1>{} {}</h1></body></html>".format(status, reason).encode("utf-8")
    response_headers = {"Content-Type": "text/html"}
    if headers:
        response_headers.update(headers)
    return build_response(status, body, response_headers)


def chunked_response(chunks, headers=None):
    """Represent a streamed body without advertising a fixed length."""
    response = build_response(200, headers=headers)
    response.headers.pop("Content-Length")
    response.headers["Transfer-Encoding"] = "chunked"
    return response._replace(body=chunks)
