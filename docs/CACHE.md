# Static representations

Each request rechecks filesystem metadata. Weak ETags include device, inode, size, mtime/ctime nanoseconds, and the selected representation. They assume an operator-managed document root and are not content hashes. If-None-Match takes precedence over If-Modified-Since; dates compare at whole-second precision.

The shared LRU stores separate identity and gzip entries within one payload-byte budget and a 256-entry cap. Default budget is 8 MiB; entries above 1 MiB bypass storage. `--cache-bytes 0` disables storage. Gzip is available for files up to 1 MiB. Its length is the compressed length and its validator differs from identity. Both representations emit `Vary: Accept-Encoding`, including 304 replies.

Metadata changes invalidate an entry when next requested. Deletion returns 404 even if old bytes remain in the bounded cache. LRU eviction removes the least recently used representation. Cache fills are serialized by a lock; file changes during a fill fail rather than caching an inconsistent snapshot. Large identity files stream in 16 KiB blocks. Gzip HEAD can load/compress a small file to obtain the selected length.

Files and symlinks must not be concurrently changed by untrusted actors: resolve/open is not an atomic filesystem sandbox. Range requests, precondition methods other than GET/HEAD, and arbitrary representation encodings are unsupported.
