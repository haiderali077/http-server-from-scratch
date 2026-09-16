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
