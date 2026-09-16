# Design decisions

## Concurrency and admission

The default bounded thread pool matches Python's blocking socket/file interfaces. Eight workers and sixteen queue slots prevent unlimited task accumulation; excess connections receive 503. A worker owns a persistent connection, so slow or idle clients consume worker capacity. Threads overlap I/O waits but do not guarantee linear CPU-parsing speedups. A readiness-loop experiment is separate from the default.

## Framing and parsing

TCP is a byte stream. SocketReader retains surplus bytes for the next message. Strict request framing rejects duplicate/conflicting boundaries. Chunking is decoded and reconstructed per hop. HEAD, 204, and 304 are bodyless. Ordered pipelining is sequential per connection, simplifying association of replies with requests.

## Deadlines and shutdown

Monotonic total budgets bound header/body reading; socket write timeouts apply per write. Idle persistence has a separate limit. Backend waits have separate connect/header/body deadlines. Shutdown stops admission, allows a configurable drain, then interrupts remaining client sockets. Operating-system DNS and active upstream waits have documented timing caveats.

## Buffering and ownership

Echo collects a bounded request body. The proxy reads and writes at most 16 KiB payload blocks, relying on blocking writes for backpressure. Stream objects own their upstream socket or file; transport closes them even on HEAD/disconnect. Once headers are committed, errors terminate the connection instead of adding a second response.

## Files and representations

Path resolution enforces document-root containment under a trusted-root assumption. Weak metadata ETags preserve cheap HEAD validation without pretending to be content hashes. Identity/gzip cache entries share an LRU byte/count budget. Rechecking metadata costs a stat but prevents ordinary stale reuse. Small fills are serialized for simple accounting; large identity files stream. Gzip negotiation can enlarge incompressible payloads.

## Proxy trust and diagnostics

Clients cannot choose backend origins. Hop-by-hop fields and Connection-nominated fields are removed. Backend Host is generated and forwarding metadata comes from the accepted peer. JSON logs distinguish completed responses from interrupted streams, omit bodies/queries, and include durations. No automatic retry of a possibly executed POST is assumed.
