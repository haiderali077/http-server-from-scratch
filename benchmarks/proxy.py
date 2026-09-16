"""Compare direct/proxied replies using matching clients, bytes, and policy."""
import argparse
import json
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
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/proxy.json"))
    parser.add_argument("--server-option", action="append", default=[])
    args = parser.parse_args()
    process = subprocess.Popen([sys.executable, "-u", "examples/backend.py", "--port", "0"], stdout=subprocess.PIPE, text=True)
    try:
        port = int(process.stdout.readline().split()[-1])
        payload = b"x" * 1024
        with RunningServer("--upstream", f"http://127.0.0.1:{port}", *args.server_option) as frontend:
            scenarios = [("direct", port, process.pid, "/index.html"), ("proxy", frontend.port, frontend.process.pid, "/api/index.html")]
            data = {"timestamp": datetime.now(timezone.utc).isoformat(), "clients": 4, "keep_alive": True, "response_bytes": 1024, "requests_per_run": args.requests, "server_options": args.server_option,
                    "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                    "note": "Shared local host; direct and proxy use identical bytes, client count and frontend persistence. CPU/RSS refer to the named server process, excluding client and other service."}
            for name, target, pid, path in scenarios:
                measure(target, 4, 20, True, payload, pid, path)
                data[name] = [measure(target, 4, args.requests, True, payload, pid, path) for _ in range(3)]
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(data, indent=2) + "\n")
            print(json.dumps({name: [{"rps": r["requests_per_second"], "p95_ms": r["p95_ms"], "errors": r["errors"]} for r in data[name]] for name in ("direct", "proxy")}))
            if any(r["errors"] for name in ("direct", "proxy") for r in data[name]):
                raise SystemExit(1)
    finally:
        process.terminate()
        process.wait(timeout=5)
        process.stdout.close()


if __name__ == "__main__":
    main()
