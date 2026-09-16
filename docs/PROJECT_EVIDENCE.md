# Project description and resume evidence

Suggested bullet:

> Built a raw-TCP HTTP/1.1 server and reverse proxy in Python with bounded concurrency, persistent connections, chunked streaming, conditional static caching, and gzip; recorded ~3.9k requests/s with ~1.37 ms p95 latency at four concurrent clients, and validated 92,000 error-free requests in a 30-second eight-client load test.

The throughput and p95 refer to the recorded 1 KiB persistent-connection resource experiment, three local runs, not every route or the final version's guaranteed performance. [Resource measurements](../benchmarks/results/resources.json) and [load/recovery evidence](../benchmarks/results/load.json) preserve configuration and revision context. Client and server shared an Apple M4 / 16 GiB machine running Python 3.13.7.

Shorter version:

> Implemented a raw-socket Python HTTP/1.1 server/reverse proxy with bounded workers, streaming, cache validators, and gzip; added protocol/failure regression tests, CI, and reproducible throughput/latency/resource benchmarks.

Use only claims you can explain and demonstrate. Do not describe this subset as full HTTP compliance or a production deployment. No personal resume file was read or modified for these examples.
