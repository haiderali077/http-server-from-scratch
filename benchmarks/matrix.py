"""Run isolated workload combinations sequentially."""
import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--output-dir", type=Path, default=Path("benchmarks/results/matrix"))
    args = parser.parse_args()
    for size in ("small", "large"):
        for connections in (1, 4, 8):
            for policy in ("fresh", "keepalive"):
                name = f"{size}-c{connections}-{policy}"
                command = [sys.executable, str(Path(__file__).with_name("run.py")),
                           "--requests", str(args.requests), "--repeat", "3", "--size", size,
                           "--connections", str(connections), "--output", str(args.output_dir / f"{name}.json")]
                if policy == "keepalive":
                    command.append("--keep-alive")
                subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True)
                print("Recorded", name, flush=True)


if __name__ == "__main__":
    main()
