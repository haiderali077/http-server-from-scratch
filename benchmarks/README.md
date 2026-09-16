# Reproducible local measurements

Run each command separately so benchmark processes do not compete with each other.

```bash
python3 benchmarks/run.py --baseline --connections 1 --requests 200 --repeat 3 --output benchmarks/results/baseline.json
python3 benchmarks/run.py --connections 4 --requests 2000 --repeat 3 --output benchmarks/results/concurrent-fresh.json
python3 benchmarks/run.py --connections 4 --requests 2000 --repeat 3 --keep-alive --output benchmarks/results/concurrent-keepalive.json
```

Results validate every response and include errors. Throughput currently counts all
attempts; only error-free runs support a successful-request throughput claim.
Clients and server run on the same machine, so client CPU, filesystem cache, loopback,
and background activity affect the measurements. Compare matching configurations;
the initial single-client baseline is not a direct ratio against four-client runs.

## Methodology and limits

The recorded host is an Apple M4 with 16 GiB RAM. Each JSON includes the exact
operating-system string, Python version, logical CPU count, timestamp, source
revision, and workload options. New resource runs also include a source SHA-256.
This is a local Linux/macOS tool using `ps`; there are no benchmark dependencies.

The generated HTML payload is 1 KiB (`small`) or 1 MiB (`large`). Warm-up is 20
attempts; measured work is repeated three times. Each client runs a closed loop:
it sends its next request after consuming the previous response. Percentiles
therefore describe this closed-loop workload, not an externally fixed arrival
rate. Queueing during overload may be understated by this design.

Request timing includes connection establishment when needed, request writing,
response parsing, and complete body reads. Errors are retained in attempt latency;
body mismatch, status mismatch, and network exceptions count as errors. There is
no deliberate network delay, and filesystem caches are warm. Background activity,
client CPU, Python scheduling, and the shared loopback interface affect results.

For a more stable sample, use 3000 attempts per repeat:

```bash
python3 benchmarks/run.py --connections 4 --requests 3000 --repeat 3 --keep-alive --output benchmarks/results/resources.json
python3 benchmarks/matrix.py --requests 300
```

Resource counters belong to the server process only. CPU percentage is relative
to one core and can exceed 100%. RSS is sampled every 50 ms; short peaks can be
missed and counters have finite precision. Measurements are descriptive, not
hardware-independent guarantees. Compare the distribution across repeats rather
than choosing a single best result.
# Direct backend versus proxy

Run `python3 benchmarks/proxy.py`. The script starts the independent demo backend and frontend, uses four clients, persistent frontend connections, 1 KiB responses, twenty warm-up requests, and three runs of 1,000 attempts. Both cases validate identical bytes. The proxy currently opens a backend connection per exchange.

Recorded median throughput was 11,934.0 requests/s direct and 4,775.1 through the proxy; median p95 was 0.615 ms direct and 1.161 ms proxied. All attempts succeeded. See `results/proxy.json`. CPU/RSS describe each named process separately, excluding the client and other service. This measures overhead for this local workload; it is not a universal ratio.
