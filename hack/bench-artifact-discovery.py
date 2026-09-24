#!/usr/bin/env python3
"""Repeat a Dagger discovery command; save timings, output, and optional wcprof.

Example (use a dedicated dev engine for an isolated wcprof dump):
  python3 hack/bench-artifact-discovery.py --runs 10 --jobs 1 \
    --output /tmp/discovery --wcprof-url http://localhost:6061 \
    -- ./bin/dagger --engine container://dagger-engine.collections-perf \
    --workspace /tmp/collections-perf/workspace check -l --all

Warmups are excluded from timing summaries and the profile. Run serially for
latency comparisons; increase --jobs to measure contention. This preserves
engine caches and does not guarantee requests reach an external rate limiter.
"""

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import threading
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wcprof-url")
    parser.add_argument("--cold-profile", action="store_true",
                        help="fresh/drained recorder: skip initialization so edited or cold inputs stay cold")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command or min(args.runs, args.jobs, args.timeout) <= 0 or args.warmups < 0:
        parser.error("provide a command, positive runs/jobs/timeout, and nonnegative warmups")
    if args.cold_profile and (not args.wcprof_url or args.warmups != 0):
        parser.error("--cold-profile requires --wcprof-url and --warmups 0 with a fresh/drained recorder")
    args.output.mkdir(parents=True, exist_ok=True)

    def run(label, profile=False):
        cmd = command[:1] + (["--profile"] if profile else []) + command[1:]
        load_before = os.getloadavg()
        start = time.perf_counter()
        with (args.output / f"{label}.out").open("wb") as out, (args.output / f"{label}.err").open("wb") as err:
            process = subprocess.Popen(cmd, stdout=out, stderr=err, start_new_session=True)
            timed_out = threading.Event()

            def expire():
                if process.poll() is not None:
                    return
                timed_out.set()
                try:
                    # Let Dagger cancel its session and write its final report.
                    os.killpg(process.pid, signal.SIGINT)
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                except ProcessLookupError:
                    pass

            timer = threading.Timer(args.timeout, expire)
            timer.daemon = True
            timer.start()
            try:
                # wait(timeout=...) polls on POSIX and can add 50 ms to short
                # runs. A separate deadline lets this wait reap immediately.
                status = process.wait()
            finally:
                timer.cancel()
                timer.join()
            if timed_out.is_set():
                status = 124
        elapsed = time.perf_counter() - start
        result = {"run": label, "seconds": elapsed, "status": status,
                  "load_average_before": load_before, "load_average_after": os.getloadavg(),
                  "stdout_sha256": hashlib.sha256((args.output / f"{label}.out").read_bytes()).hexdigest()}
        print(json.dumps(result), flush=True)
        return result

    for i in range(args.warmups):
        if run(f"warmup-{i}")["status"]:
            raise SystemExit("warmup failed; inspect saved stderr")

    def dump(name):
        url = args.wcprof_url.rstrip("/") + "/debug/wcprof/dump"
        with urllib.request.urlopen(url, timeout=60) as response:
            with (args.output / name).open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)

    if args.wcprof_url and not args.cold_profile:
        # Enable a tiny profiled command to initialize the recorder, then drain
        # any earlier data before collecting the measured runs.
        if run("profile-init", profile=True)["status"]:
            raise SystemExit("profile initialization failed; inspect saved stderr")
        dump("warmup.wcprof")
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda i: run(f"run-{i}", profile=bool(args.wcprof_url)), range(args.runs)))
    elapsed = time.perf_counter() - start
    if args.wcprof_url:
        dump("runs.wcprof")
    times = sorted(r["seconds"] for r in results)
    summary = {"command": command, "cwd": os.getcwd(), "cpu_count": os.cpu_count(), "jobs": args.jobs, "runs": results,
               "profiled": bool(args.wcprof_url), "elapsed_seconds": elapsed,
               "commands_per_second": sum(r["status"] == 0 for r in results) / elapsed,
               "median_seconds": statistics.median(times),
               "p95_seconds": times[math.ceil(0.95 * len(times)) - 1],
               "max_seconds": max(times), "failures": sum(r["status"] != 0 for r in results),
               "distinct_outputs": len({r["stdout_sha256"] for r in results})}
    (args.output / "results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}), flush=True)
    if summary["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
