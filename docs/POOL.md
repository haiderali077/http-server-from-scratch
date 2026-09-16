# Backend connection pooling

`--upstream-pool-size 8` enables up to eight exclusive connections per backend. Default zero preserves a connection per request. The connect timeout also bounds waiting for a pool lease.

A response must be fully consumed with valid fixed/chunked/bodyless framing, no buffered surplus bytes, and no close instruction before its socket returns to the idle pool. Truncation, disconnect, timeout, client write failure, and close-delimited bodies discard the socket. HTTP/1.0 defaults to close. Readable idle sockets are discarded before leasing because they may contain EOF or unsolicited bytes.

The pool never automatically retries a failed operation; a request may already have reached the backend. In particular, retrying POST could duplicate an action. A stale-socket race after the readiness check can therefore produce one gateway error rather than silent replay. Pool shutdown closes idle sockets and returned active leases.

Reproduce matching measurements:

```sh
python3 benchmarks/proxy.py --output benchmarks/results/pool-disabled.json
python3 benchmarks/proxy.py --server-option=--upstream-pool-size --server-option=8 --output benchmarks/results/pool-enabled.json
```

Both artifacts retain the same source fingerprint and workload, plus run-level CPU/RSS, errors, throughput, and percentiles. Pooling is optional because reuse can help connection-heavy workloads while adding synchronization and stale-connection handling.

Recorded median proxy throughput was 3,102.3 requests/s with pooling disabled and 5,780.3 enabled; median p95 was 2.124 ms and 0.981 ms. All attempts validated successfully. The disabled runs varied considerably (3,020–4,434 requests/s), so this local observation is not a stable universal improvement factor.
