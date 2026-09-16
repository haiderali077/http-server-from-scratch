"""Convert received HTTP text into request data without touching sockets."""

import re
from typing import Dict, NamedTuple
from urllib.parse import unquote


TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class HTTPError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class HTTPRequest(NamedTuple):
    method: str
    path: str
    query: str
    version: str
    headers: Dict[str, str]
    body: bytes = b""


def parse_request_target(target):
    """Split an HTTP request target into a decoded path and raw query text.

    A query has application-specific rules, so it remains raw for a future
    router to interpret. The path is percent-decoded once before file lookup.
    """
    if not target.startswith("/") or "#" in target:
        raise HTTPError("Only origin-form paths without fragments are supported")
    raw_path, separator, query = target.partition("?")
    for value in (raw_path, query if separator else ""):
        if re.search(r"%(?![0-9A-Fa-f]{2})", value):
            raise HTTPError("Request target has invalid percent encoding")

    try:
        path = unquote(raw_path, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise HTTPError("Request path has invalid UTF-8 percent encoding") from error
    if any(ord(character) < 32 or character == "\\" for character in path):
        raise HTTPError("Invalid character in request path")
    return path, query


def parse_request(message, max_body_bytes=1048576):
    """Validate the supported HTTP/1.0 and HTTP/1.1 request header syntax."""
    lines = message.split("\r\n")
    parts = lines[0].split()
    if len(parts) != 3 or not TOKEN.fullmatch(parts[0]):
        raise HTTPError("Invalid request line")
    if parts[2] not in ("HTTP/1.0", "HTTP/1.1"):
        raise HTTPError("Unsupported HTTP version", 505)

    headers = {}
    for line in lines[1:]:
        if not line:
            break
        name, separator, value = line.partition(":")
        if not separator or not TOKEN.fullmatch(name):
            raise HTTPError("Invalid header name or separator")
        if any((ord(character) < 32 and character != "\t") or ord(character) == 127 for character in value):
            raise HTTPError("Invalid control character in header")
        key = name.lower()
        if key == "host" and key in headers:
            raise HTTPError("Duplicate Host header")
        headers[key] = headers[key] + "," + value.strip() if key in headers else value.strip()

    host = headers.get("host", "")
    if parts[2] == "HTTP/1.1" and (not host or any(character.isspace() for character in host) or "," in host):
        raise HTTPError("HTTP/1.1 requires one valid Host header")
    if "content-length" in headers:
        length = headers["content-length"]
        if not re.fullmatch(r"[0-9]+", length):
            raise HTTPError("Invalid Content-Length")
        if len(length) > 12 or int(length) > max_body_bytes:
            raise HTTPError("Request body exceeds configured limit", 413)

    path, query = parse_request_target(parts[1])
    return HTTPRequest(
        method=parts[0],
        path=path,
        query=query,
        version=parts[2],
        headers=headers,
    )
