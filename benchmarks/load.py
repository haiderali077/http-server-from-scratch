"""Sustained validated traffic, resource drift, and post-load recovery."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run import measure, process_resources
from tests.support import RunningServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/load.json"))
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("Duration must be positive")
    batches = []
    with RunningServer() as server:
        payload = b"x" * 1024
        (server.root / "index.html").write_bytes(payload)
        pid = server.process.pid
        initial = process_resources(pid)
        start = time.monotonic()
        while time.monotonic() - start < args.seconds:
            batches.append(measure(server.port, 8, 1000, True, payload, pid))
        elapsed = time.monotonic() - start
        recovery = measure(server.port, 1, 20, False, payload, pid)
        final = process_resources(pid)
    drift = final[1] - initial[1] if initial and final else None
    result = {"duration_seconds": round(elapsed, 3), "clients": 8, "response_bytes": 1024,
              "attempts": sum(batch["attempts"] for batch in batches),
              "errors": sum(batch["errors"] for batch in batches), "batches": batches,
              "recovery": recovery, "rss_drift_kib": drift,
              "memory_drift_budget_kib": 65536,
              "checks_passed": all(batch["errors"] == 0 for batch in batches) and
                  recovery["errors"] == 0 and drift is not None and drift < 65536,
              "note": "Local closed-loop soak; observed drift is not a proof of a universal memory bound."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "batches"}))
    if not result["checks_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
