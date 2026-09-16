"""Convert received HTTP text into request data without touching sockets."""

from typing import Dict, NamedTuple


class HTTPRequest(NamedTuple):
    method: str
    path: str
    version: str
    headers: Dict[str, str]


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

    return HTTPRequest(
        method=parts[0],
        path=parts[1],
        version=parts[2] if len(parts) > 2 else "",
        headers=headers,
    )
