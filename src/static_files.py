"""Map requests to local files and return response data without socket I/O."""

import os
import hashlib
import gzip
from pathlib import Path
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

if __package__:
    from .http_response import build_response, error_response, format_http_date
    from .encoding import qualities
else:
    from http_response import build_response, error_response, format_http_date
    from encoding import qualities


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


class PathOutsideDocumentRoot(ValueError):
    """Raised when a requested resource resolves outside the document root."""


def get_content_type(filename):
    return CONTENT_TYPES.get(os.path.splitext(filename)[1], "application/octet-stream")


def resolve_filename(path, document_root=DEFAULT_DOCUMENT_ROOT):
    """Map a URL path to a local path contained by the document root."""
    document_root = Path(document_root).resolve()
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

    candidate = (document_root / filename).resolve()
    try:
        candidate.relative_to(document_root)
    except ValueError as error:
        raise PathOutsideDocumentRoot("Requested path escapes the document root") from error
    return candidate


def is_not_modified(last_modified, if_modified_since):
    if not if_modified_since:
        return False
    try:
        client_date = parsedate_to_datetime(if_modified_since)
        if client_date.tzinfo is None:
            client_date = client_date.replace(tzinfo=timezone.utc)
        return int(last_modified) <= int(client_date.timestamp())
    except (ValueError, TypeError, OverflowError):
        return False


def file_signature(stat):
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def file_etag(stat, representation="identity"):
    # Weak metadata validator: no claim of byte identity under arbitrary stat manipulation.
    digest = hashlib.sha256(repr((file_signature(stat), representation)).encode()).hexdigest()[:24]
    return f'W/"{digest}"'


def etag_matches(condition, etag):
    if condition is None:
        return False
    return any(value.strip() == "*" or value.strip().removeprefix("W/") == etag.removeprefix("W/")
               for value in condition.split(","))


class FileBody:
    def __init__(self, filename, size):
        self.resource = open(filename, "rb")
        self.size = size
    def __iter__(self):
        remaining = self.size
        while remaining:
            data = self.resource.read(min(16384, remaining))
            if not data:
                raise OSError("File shortened during response")
            remaining -= len(data)
            yield data
    def close(self):
        self.resource.close()


def serve_file(request, document_root=DEFAULT_DOCUMENT_ROOT, cache=None):
    """Serve GET representations and bodyless HEAD metadata."""
    if request.method not in ("GET", "HEAD"):
        return error_response(405, {"Allow": "GET, HEAD"})

    try:
        filename = resolve_filename(request.path, document_root)
        extension = os.path.splitext(filename)[1].lower()
        if extension and extension not in CONTENT_TYPES:
            return error_response(415)
        if not os.path.exists(filename):
            return error_response(404)

        stat = filename.stat()
        gzip_q, identity_q = qualities(request.headers.get("accept-encoding"))
        can_gzip = stat.st_size <= 1048576
        compressed = can_gzip and gzip_q > 0 and gzip_q >= identity_q
        if not compressed and identity_q == 0:
            return error_response(406, {"Vary": "Accept-Encoding"})
        last_modified = stat.st_mtime
        headers = {"Last-Modified": format_http_date(last_modified), "ETag": file_etag(stat, "gzip" if compressed else "identity"), "Vary": "Accept-Encoding"}
        if compressed:
            headers["Content-Encoding"] = "gzip"
        condition = request.headers.get("if-none-match")
        unchanged = (etag_matches(condition, headers["ETag"]) if condition is not None
                     else is_not_modified(last_modified, request.headers.get("if-modified-since")))
        if unchanged:
            return build_response(304, headers=headers)

        headers["Content-Type"] = get_content_type(filename)
        if request.method == "HEAD" and not compressed:
            response = build_response(200, headers=headers)
            response.headers["Content-Length"] = str(os.path.getsize(filename))
            return response
        if stat.st_size > (cache.max_entry if cache else 1048576):
            response = build_response(200, headers=headers)
            response.headers["Content-Length"] = str(stat.st_size)
            return response._replace(body=FileBody(filename, stat.st_size))
        def load():
            with open(filename, "rb") as resource:
                body = resource.read(1048577)
            if file_signature(filename.stat()) != file_signature(stat):
                raise OSError("File changed during cache fill")
            return body
        body = cache.get((str(filename), "identity"), file_signature(stat), load) if cache else load()
        if compressed:
            compress = lambda: gzip.compress(body, mtime=0)
            body = cache.get((str(filename), "gzip"), file_signature(stat), compress) if cache else compress()
        if request.method == "HEAD":
            response = build_response(200, headers=headers)
            response.headers["Content-Length"] = str(len(body))
            return response
        return build_response(200, body, headers)
    except PathOutsideDocumentRoot:
        return error_response(403)
    except OSError:
        # File access failures belong here, not in the socket transport layer.
        return error_response(404)
