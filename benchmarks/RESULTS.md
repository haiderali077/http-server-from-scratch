# Recorded local results

Apple M4, 16 GiB RAM, macOS 26.3, Python 3.13.7. Client and server share the host.

Each row summarizes three recorded runs. These are closed-loop measurements, not capacity guarantees.

| Workload | Clients | Median requests/s | Median p95 (ms) | Errors |
|---|---:|---:|---:|---:|
| baseline.json | 1 | 5200.6 | 0.217 | 0 |
| concurrent-fresh.json | 4 | 3291.7 | 1.570 | 0 |
| concurrent-keepalive.json | 4 | 3601.2 | 1.609 | 0 |
| resources.json | 4 | 3925.3 | 1.367 | 0 |

The original single-client baseline is faster in this tiny workload. Its client count differs from the four-client cases; these rows do not establish a speedup ratio.

The thread pool allows overlapping socket waits and isolates slow clients, but scheduling, locking, per-request parsing, and the shared load generator add overhead. CPU samples above one core reflect total process CPU, not whole-machine utilization.

The matrix in `results/matrix/` varies payload size, client count, and connection reuse. A 30-second soak completed 92,000 validated requests with no errors and passed a subsequent recovery check. Observed memory drift passed the 64 MiB regression budget; this does not prove a universal bound.

Likely costs to investigate: repeated file opens/reads, connection setup, worker scheduling, and Python parsing. These are hypotheses, not profiler-confirmed bottlenecks. Compare matching workloads before attributing any difference to one feature.

See [methodology](README.md), [generator](run.py), [matrix](matrix.py), [load test](load.py), and the raw JSON artifacts. Regenerate with `python3 benchmarks/report.py`.
