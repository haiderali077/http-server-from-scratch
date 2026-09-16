"""Compare cache and gzip under identical payloads and client workloads."""
import argparse
import gzip
import json
import random
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.run import measure
from tests.support import RunningServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/cache.json"))
    args = parser.parse_args()
    data = {"timestamp": datetime.now(timezone.utc).isoformat(), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "clients": 4, "requests_per_run": args.requests, "keep_alive": True,
            "note": "Local shared host; 20 warm-up attempts, three runs. CPU/RSS measure server only. Random bytes use a fixed seed; text deliberately compresses well.", "workloads": {}}
    payloads = {"text": (b"hello HTTP caching and compression\n" * 1000)[:32768], "random": random.Random(42).randbytes(32768)}
    for name, payload in payloads.items():
        data["workloads"][name] = {}
        for policy, budget, encoded in [("uncached", "0", False), ("cached", "8388608", False), ("gzip_cached", "8388608", True)]:
            expected = gzip.compress(payload, mtime=0) if encoded else payload
            with RunningServer("--cache-bytes", budget) as server:
                (server.root / "index.html").write_bytes(payload)
                headers = {"Accept-Encoding": "gzip" if encoded else "identity"}
                measure(server.port, 4, 20, True, expected, server.process.pid, headers=headers)
                runs = [measure(server.port, 4, args.requests, True, expected, server.process.pid, headers=headers) for _ in range(3)]
                data["workloads"][name][policy] = {"original_bytes": len(payload), "wire_body_bytes": len(expected), "runs": runs}
                print(name, policy, round(sum(r["requests_per_second"] for r in runs) / 3), "rps", len(expected), "bytes")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    if any(r["errors"] for policies in data["workloads"].values() for entry in policies.values() for r in entry["runs"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
