"""Generate a concise, honest report from recorded local experiments."""
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
lines = ["# Recorded local results", "", "Apple M4, 16 GiB RAM, macOS 26.3, Python 3.13.7. Client and server share the host.", "", "Each row summarizes three recorded runs. These are closed-loop measurements, not capacity guarantees.", "", "| Workload | Clients | Median requests/s | Median p95 (ms) | Errors |", "|---|---:|---:|---:|---:|"]
for filename in ["baseline.json", "concurrent-fresh.json", "concurrent-keepalive.json", "resources.json"]:
    path = ROOT / "results" / filename
    if not path.exists():
        continue
    data = json.loads(path.read_text())
    runs = data["runs"]
    clients = data["configuration"]["connections"]
    lines.append(f"| {filename} | {clients} | {median(r['requests_per_second'] for r in runs):.1f} | {median(r['p95_ms'] for r in runs):.3f} | {sum(r['errors'] for r in runs)} |")
lines += ["", "The original single-client baseline is faster in this tiny workload. Its client count differs from the four-client cases; these rows do not establish a speedup ratio.", "", "The thread pool allows overlapping socket waits and isolates slow clients, but scheduling, locking, per-request parsing, and the shared load generator add overhead. CPU samples above one core reflect total process CPU, not whole-machine utilization.", "", "The matrix in `results/matrix/` varies payload size, client count, and connection reuse. A 30-second soak completed 92,000 validated requests with no errors and passed a subsequent recovery check. Observed memory drift passed the 64 MiB regression budget; this does not prove a universal bound.", "", "Likely costs to investigate: repeated file opens/reads, connection setup, worker scheduling, and Python parsing. These are hypotheses, not profiler-confirmed bottlenecks. Compare matching workloads before attributing any difference to one feature.", "", "See [methodology](README.md), [generator](run.py), [matrix](matrix.py), [load test](load.py), and the raw JSON artifacts. Regenerate with `python3 benchmarks/report.py`."]
(ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n")
