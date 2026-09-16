# Reproducible engineering scenarios

## Parsing and timing precision

Run `python3 -m unittest tests.test_conditional -v`. The date round-trip uses a file timestamp with fractional seconds and returns the actual Last-Modified value as If-Modified-Since. It reproduces the original precision mismatch and checks a bodyless 304. ETag tests check precedence and edits.

## Throughput tradeoffs

Run `python3 benchmarks/proxy.py` and `python3 benchmarks/cache.py`. Compare matching client counts, bytes, and policy before attributing a change to concurrency. The direct/proxy run exposes the extra hop's overhead; text/random cases expose compression's workload dependence. Raw measurements retain errors and tail latency. These observations motivate profiling rather than prove a particular internal function is the bottleneck.

## Failure after commitment

Run `python3 -m unittest tests.test_proxy_failures -v`. A malformed upstream returns 502; a delayed header returns 504. A truncated fixed-length body retains the already-sent 200 headers and closes without inserting a second status line. A synchronization handshake proves bytes arrive before the backend finishes.

For a manual outage, start the two-service demo, stop the backend, request `/api/health`, and verify local `/health` still works. Restart the backend and try the API again. Add `--access-log /tmp/http-access.jsonl --error-log /tmp/http-error.jsonl` to inspect completion and error records.
