"""Map requests to local files and return response data without socket I/O."""

import os
from pathlib import Path
import re
from datetime import datetime, timezone

if __package__:
    from .http_response import build_response, error_response, format_http_date
else:
    from http_response import build_response, error_response, format_http_date


CONTENT_TYPES = {
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".pdf": "application/pdf",
}
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf"}
DEFAULT_DOCUMENT_ROOT = Path(__file__).resolve().parent


def get_content_type(filename):
    return CONTENT_TYPES.get(os.path.splitext(filename)[1], "application/octet-stream")


def resolve_filename(path, document_root=DEFAULT_DOCUMENT_ROOT):
    """Apply the existing route rules relative to the configured document root.

    Safe path containment is an upcoming roadmap item. Replacing '..' is
    retained for compatibility, not considered secure.
    """
    document_root = Path(document_root)
    filename = "index.html" if path in ("/", "") else path.lstrip("/")
    if filename.endswith("/"):
        filename += "index.html"

    if not re.search(r"\.[a-zA-Z]+$", filename):
        if os.path.isdir(document_root / filename):
            filename = os.path.join(filename, "index.html")
        elif os.path.exists(document_root / (filename + ".html")):
            filename += ".html"
        elif os.path.exists(document_root / (filename + ".htm")):
            filename += ".htm"
        else:
            filename += ".html"

    return document_root / filename.replace("..", "")


def is_not_modified(last_modified, if_modified_since):
    if not if_modified_since:
        return False
    try:
        client_date = datetime.strptime(
            if_modified_since, "%a, %d %b %Y %H:%M:%S %Z"
        ).replace(tzinfo=timezone.utc)
        file_date = datetime.fromtimestamp(last_modified, timezone.utc)
        return file_date <= client_date
    except ValueError:
        return False


def serve_file(request, document_root=DEFAULT_DOCUMENT_ROOT):
    """Return an HTTPResponse for the current GET-only static file service."""
    if request.method != "GET":
        return error_response(405, {"Allow": "GET"})

    try:
        filename = resolve_filename(request.path, document_root)
        extension = os.path.splitext(filename)[1].lower()
        if extension and extension not in CONTENT_TYPES:
            return error_response(415)
        if not os.path.exists(filename):
            return error_response(404)

        last_modified = os.path.getmtime(filename)
        headers = {"Last-Modified": format_http_date(last_modified)}
        if is_not_modified(last_modified, request.headers.get("if-modified-since")):
            return build_response(304, headers=headers)

        if extension in BINARY_EXTENSIONS:
            with open(filename, "rb") as resource:
                body = resource.read()
        else:
            with open(filename, "r", encoding="utf-8") as resource:
                body = resource.read().encode("utf-8")

        headers["Content-Type"] = get_content_type(filename)
        return build_response(200, body, headers)
    except OSError:
        # File access failures belong here, not in the socket transport layer.
        return error_response(404)
