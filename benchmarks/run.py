"""Repeatable local HTTP measurements; no external benchmark dependencies."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import http.client
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.support import RunningServer


def process_resources(pid):
    try:
        output = subprocess.check_output(["ps", "-o", "time=", "-o", "rss=", "-p", str(pid)], text=True)
        cpu, rss = output.split()
        seconds = 0.0
        for part in cpu.split(":"):
            seconds = seconds * 60 + float(part)
        return seconds, int(rss)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


class ResourceSampler:
    def __init__(self, pid):
        self.pid = pid
        self.first = process_resources(pid) if pid else None
        self.samples = [self.first] if self.first else []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.collect, daemon=True)

    def collect(self):
        while not self.stop.wait(0.05):
            sample = process_resources(self.pid)
            if sample:
                self.samples.append(sample)

    def start(self):
        if self.first:
            self.thread.start()

    def finish(self, elapsed):
        self.stop.set()
        if self.thread.is_alive():
            self.thread.join(1)
        last = process_resources(self.pid) if self.first else None
        if not last:
            return {"resources_available": False}
        self.samples.append(last)
        cpu_seconds = max(0.0, last[0] - self.first[0])
        return {"resources_available": True, "server_cpu_seconds": round(cpu_seconds, 3),
                "server_cpu_percent_one_core": round(100 * cpu_seconds / elapsed, 1),
                "rss_kib_start": self.first[1], "rss_kib_end": last[1],
                "rss_kib_observed_max": max(sample[1] for sample in self.samples),
                "resource_sampling_seconds": 0.05}


@contextmanager
def baseline_server(payload):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        original = subprocess.check_output(["git", "show", "678b2d0:src/webserver.py"], cwd=ROOT)
        (root / "baseline.py").write_bytes(original)
        (root / "index.html").write_bytes(payload)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        process = subprocess.Popen([sys.executable, str(root / "baseline.py"), "-p", str(port)],
                                   cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=1).close()
                    break
                except OSError:
                    time.sleep(0.02)
            else:
                raise RuntimeError("Baseline did not start")
            yield port, process.pid
        finally:
            process.terminate()
            process.wait(timeout=5)


def measure(port, concurrency, requests, keep_alive, expected, pid=None):
    def worker(count):
        client = None
        samples = []
        try:
            for unused in range(count):
                started = time.perf_counter()
                error = None
                transferred = 0
                try:
                    if client is None:
                        client = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    client.request("GET", "/index.html", headers={"Connection": "keep-alive" if keep_alive else "close"})
                    response = client.getresponse()
                    body = response.read()
                    transferred = len(body)
                    if response.status != 200 or body != expected:
                        error = f"status={response.status}, bytes={len(body)}"
                except (OSError, http.client.HTTPException) as failure:
                    error = type(failure).__name__
                samples.append((1000 * (time.perf_counter() - started), error, transferred))
                if not keep_alive or error:
                    client.close()
                    client = None
        finally:
            if client:
                client.close()
        return samples

    counts = [requests // concurrency + (index < requests % concurrency) for index in range(concurrency)]
    resources = ResourceSampler(pid)
    resources.start()
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        samples = [sample for result in pool.map(worker, counts) for sample in result]
    elapsed = time.perf_counter() - start
    latencies = sorted(sample[0] for sample in samples)

    def percentile(fraction):
        return round(latencies[min(len(latencies) - 1, int((len(latencies) - 1) * fraction))], 3)

    return {
        **resources.finish(elapsed),
        "attempts": len(samples), "errors": sum(sample[1] is not None for sample in samples),
        "error_examples": sorted({sample[1] for sample in samples if sample[1]}),
        "seconds": round(elapsed, 4), "requests_per_second": round(len(samples) / elapsed, 1),
        "p50_ms": percentile(0.5), "p95_ms": percentile(0.95), "p99_ms": percentile(0.99),
        "payload_bytes": sum(sample[2] for sample in samples),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--connections", type=int, default=1)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--keep-alive", action="store_true")
    parser.add_argument("--size", choices=("small", "large"), default="small")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.connections, args.requests, args.repeat, args.warmup) < 1:
        parser.error("Counts must be positive")
    payload = b"x" * (1024 if args.size == "small" else 1048576)
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
        "machine": platform.machine(), "cpu_count": os.cpu_count(), "python": sys.version,
        "server_commit": "678b2d0" if args.baseline else subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "generator": "stdlib http.client, clients and server on the same machine",
        "configuration": {key: value for key, value in vars(args).items() if key != "output"},
        "response_bytes": len(payload), "latency_scope": "all attempts, including errors",
        "server_source_sha256": hashlib.sha256(b"".join(path.read_bytes() for path in sorted((ROOT / "src").glob("*.py")))).hexdigest() if not args.baseline else hashlib.sha256(subprocess.check_output(["git", "show", "678b2d0:src/webserver.py"], cwd=ROOT)).hexdigest(),
        "resource_note": "ps CPU counters and sampled RSS; sampled maximum is not an exact OS peak",
    }
    context = baseline_server(payload) if args.baseline else RunningServer()
    with context as server:
        if args.baseline:
            port, pid = server
        else:
            (server.root / "index.html").write_bytes(payload)
            port, pid = server.port, server.process.pid
        result["warmup"] = measure(port, args.connections, args.warmup, args.keep_alive, payload, pid)
        result["runs"] = [measure(port, args.connections, args.requests, args.keep_alive, payload, pid)
                          for unused in range(args.repeat)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runs": result["runs"]}))


if __name__ == "__main__":
    main()
