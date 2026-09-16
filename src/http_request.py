"""Convert received HTTP text into request data without touching sockets."""

import re
from typing import Dict, NamedTuple
from urllib.parse import unquote


class HTTPRequest(NamedTuple):
    method: str
    path: str
    query: str
    version: str
    headers: Dict[str, str]


def parse_request_target(target):
    """Split an HTTP request target into a decoded path and raw query text.

    A query has application-specific rules, so it remains raw for a future
    router to interpret. The path is percent-decoded once before file lookup.
    """
    raw_path, separator, query = target.partition("?")
    for value in (raw_path, query if separator else ""):
        if re.search(r"%(?![0-9A-Fa-f]{2})", value):
            raise ValueError("Request target has invalid percent encoding")

    try:
        path = unquote(raw_path, encoding="utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Request path has invalid UTF-8 percent encoding") from error
    return path, query


def parse_request(message):
    """Parse the existing request subset; raise ValueError if no method/path exists.

    Header names are normalized for case-insensitive lookup. Full protocol
    validation and incremental reads are separate roadmap items.
    """
    lines = message.split("\r\n")
    parts = lines[0].split()
    if len(parts) < 2:
        raise ValueError("A request must include a method and path")

    headers = {}
    for line in lines[1:]:
        if not line:
            break
        name, separator, value = line.partition(":")
        if separator:
            # Preserve the original behavior of using the first matching header.
            headers.setdefault(name.lower(), value.strip())

    path, query = parse_request_target(parts[1])
    return HTTPRequest(
        method=parts[0],
        path=path,
        query=query,
        version=parts[2] if len(parts) > 2 else "",
        headers=headers,
    )
