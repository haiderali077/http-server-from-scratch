# Performance evidence

Measurements were made on an Apple M4 / 16 GiB machine with Python 3.13.7. Client and servers share the host. All experiments are closed-loop, so they do not establish capacity under a fixed external arrival rate.

| Experiment | Observed result | Reproduce / raw evidence |
|---|---|---|
| Original sequential baseline | One-client tiny workload can outperform the concurrent implementation | [Generator](../benchmarks/run.py), [baseline JSON](../benchmarks/results/baseline.json) |
| Connection reuse | Four-client median 3,601 keep-alive vs 3,291 fresh requests/s | [Methodology](../benchmarks/README.md), [keep-alive](../benchmarks/results/concurrent-keepalive.json), [fresh](../benchmarks/results/concurrent-fresh.json) |
| Concurrency/payload matrix | 1/4/8 clients; 1 KiB/1 MiB; fresh/persistent; no recorded errors | [Matrix runner](../benchmarks/matrix.py), [artifacts](../benchmarks/results/matrix) |
| Sustained recovery | 92,000 valid requests in 30.169 s, then 20 successful recovery requests | [Load test](../benchmarks/load.py), [JSON](../benchmarks/results/load.json) |
| Proxy hop | Median 11,934.0 direct vs 4,775.1 proxied requests/s; p95 0.615 vs 1.161 ms | [Comparison](../benchmarks/proxy.py), [JSON](../benchmarks/results/proxy.json) |
| Static cache/gzip | Warm repetitive text 32,768 → 167 bytes; random 32,768 → 32,796 | [Comparison](../benchmarks/cache.py), [JSON](../benchmarks/results/cache.json) |

Each JSON retains run-level results, errors, workload parameters, and timing scope. Newer resource-instrumented experiments include server CPU and sampled RSS. Sampled maxima may miss short peaks. The original baseline was captured before adding resource sampling. Warm compression runs do not isolate cold-miss cost.

See the [generated results overview](../benchmarks/RESULTS.md) and [complete methodology](../benchmarks/README.md). Compare matching client counts, payloads, and connection policies. Do not derive a speedup ratio from the original one-client case and later four-client cases.
