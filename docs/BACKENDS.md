# Multiple configured backends

Repeat `--upstream http://127.0.0.1:8000 --upstream http://127.0.0.1:8001` to enable round-robin over up to eight distinct origins. Single-origin mode keeps its existing behavior and does not require a health endpoint. Each multi-origin backend must return 200 for `GET /health`.

Multi-origin mode performs lazy active probes on the first request and at most once per second of traffic. Probes use dedicated short-lived connections, with connect/header phases each capped at 0.2 seconds or the configured shorter deadline. Probes are serialized; the triggering request includes their delay. With no traffic there are no periodic probes. This is a deliberately simple health mechanism.

Only healthy origins are selected; all unhealthy returns 503. A selected origin's gateway failure marks it unhealthy until the next probe cycle. That request gets its original 502/504 and is never replayed to another origin. Health probes can restore eligibility. Each origin has its own optional bounded connection pool. No sticky sessions, weighted policy, or distributed health state is implemented.
