# Supported HTTP subset

Frontend accepts origin-form requests with HTTP/1.0 or HTTP/1.1; HTTP/1.1 requires exactly one nonempty Host. It emits HTTP/1.1 responses. HTTP/1.0 connections close after one request. HTTP/1.1 supports persistence and ordered pipelining, with a configurable maximum request count.

Local files support GET/HEAD, index and extension fallback, binary bytes, Last-Modified, weak ETags, If-None-Match precedence, and bounded gzip negotiation. `/echo` accepts POST; `/health` and `/stream` accept GET/HEAD. Proxy routes forward methods supported by the backend except CONNECT; no tunnel is created.

Request bodies use one valid Content-Length or exactly `Transfer-Encoding: chunked`. Duplicate lengths, conflicting framing, unsupported transfer codings, malformed syntax, and request trailers are rejected. Chunk-size lines are limited to 128 bytes; trailers are unsupported on either hop. Expect requests return 417; 100-continue upload negotiation is not implemented.

Upstream replies support fixed, chunked, close-delimited, HEAD, 204, and 304 bodies. Limited informational replies are consumed; 101 upgrades are rejected. Set-Cookie fields remain separate. Upstream headers are capped at 32 KiB and decoded bodies at 64 MiB. Failure after headers closes the connection; it cannot change the already-sent status.

Defaults: frontend headers 32 KiB, decoded body 1 MiB, 8 worker threads, 16 queued connections, 100 exchanges per connection, cache 8 MiB payload/256 entries/1 MiB per entry. Header/body deadlines cover each entire read phase. Writes have a per-write timeout. Thread-pool idle persistent clients occupy workers. Queue waiting is bounded by capacity rather than a separate absolute queue deadline.

Not implemented: full HTTP compliance, HTTP/2 or HTTP/3, WebSockets, CONNECT, absolute-form forward proxying, request trailers, range/If-Range, all preconditions, multipart/form decoding, virtual-host authorization, response caching for backend resources, rate limiting, and arbitrary untrusted filesystem mutation. File extension filtering is an explicit demo policy (415 for unsupported extensions).

Document-root resolution rejects escapes and existing out-of-root symlinks. Resolve/open is not an atomic sandbox against concurrent symlink replacement. Operate with a trusted document root and fixed trusted backend configuration. Backend DNS resolution may exceed socket deadlines. JSON logs omit bodies and queries but decoded paths can still contain application data.

Measurements are local experiments, not production capacity promises. This project is for learning and protocol experimentation.
