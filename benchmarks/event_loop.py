"""Matching workload for thread ownership versus readiness-managed persistence."""
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run import measure
from tests.support import RunningServer

data = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "requests_per_run": 1000, "response_bytes": 1024,
        "note": "Shared local host. Hybrid selectors manages idle sockets; bounded workers still do active reads/writes/application work. Same cached bytes, persistent clients, warm-up 20, three repeats.", "runs": {}}
for mode in ("threads", "selectors"):
    data["runs"][mode] = {}
    for clients in (1, 4, 8):
        with RunningServer("--mode", mode) as server:
            payload = b"x" * 1024
            (server.root / "index.html").write_bytes(payload)
            measure(server.port, clients, 20, True, payload, server.process.pid)
            runs = [measure(server.port, clients, 1000, True, payload, server.process.pid) for _ in range(3)]
            data["runs"][mode][str(clients)] = runs
            print(mode, clients, round(sum(r["requests_per_second"] for r in runs) / 3), "rps")
Path("benchmarks/results/selectors.json").write_text(json.dumps(data, indent=2) + "\n")
if any(r["errors"] for modes in data["runs"].values() for runs in modes.values() for r in runs):
    raise SystemExit(1)
