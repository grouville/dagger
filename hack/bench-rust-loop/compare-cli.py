#!/usr/bin/env python3
"""Alternate two CLI configurations on the same command; no resets or edits.

This isolates CLI changes, or module settings in prepared workspaces. It is NOT
a native Cargo or invalidation benchmark: either side may reuse an earlier execution.
Environment, engine and CLI-state isolation belong to the caller.
"""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--workdir", default=Path.cwd(), type=Path)
    parser.add_argument("--before-workdir", type=Path, help="Optional prepared workspace override for the before side")
    parser.add_argument("--after-workdir", type=Path, help="Optional prepared workspace override for the after side")
    parser.add_argument("--samples", default=30, type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.samples < 1:
        parser.error("provide at least one sample and a command after --")
    binaries = {"before": args.before.resolve(), "after": args.after.resolve()}
    workdirs = {"before": (args.before_workdir or args.workdir).resolve(),
                "after": (args.after_workdir or args.workdir).resolve()}
    root = Path(tempfile.mkdtemp(prefix="dagger-rust-cli-pair-"))
    print(root, flush=True)
    metadata = {
        "command": command,
        "workdir": str(args.workdir.resolve()),
        "workdirs": {side: str(path) for side, path in workdirs.items()},
        "samples": args.samples,
        "warmup_pairs": 1,
        "engine": os.getenv("DAGGER_ENGINE"),
        "do_not_track": os.getenv("DO_NOT_TRACK"),
        "native_wcprof": "--profile" in command,
        "local_otel": os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
        "binary_sha256": {},
    }
    for side, binary in binaries.items():
        with binary.open("rb") as source:
            metadata["binary_sha256"][side] = hashlib.file_digest(source, "sha256").hexdigest()
    (root / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    samples = {side: [] for side in binaries}
    with (root / "processes.jsonl").open("x") as records, (root / "timings.csv").open("x") as times:
        writer = csv.writer(times)
        writer.writerow(["sample", "side", "milliseconds", "warmup"])
        for sample in range(args.samples + 1):
            for side in (binaries if sample % 2 == 0 else reversed(binaries)):
                label = f"{side}-{sample}"
                argv = [str(binaries[side]), *command]
                with (root / f"{label}.log").open("xb") as log:
                    wall_start, start = time.time_ns(), time.perf_counter_ns()
                    result = subprocess.run(argv, cwd=workdirs[side], stdout=log, stderr=subprocess.STDOUT)
                    end, wall_end = time.perf_counter_ns(), time.time_ns()
                elapsed = (end - start) / 1e6
                records.write(json.dumps(dict(label=label, command=argv, start_unix_ns=wall_start,
                                              end_unix_ns=wall_end, milliseconds=elapsed,
                                              exit_code=result.returncode)) + "\n")
                records.flush()
                writer.writerow([sample, side, elapsed, sample == 0])
                times.flush()
                if result.returncode:
                    raise SystemExit(f"{label} exited {result.returncode}; see {root / (label + '.log')}")
                if sample:
                    samples[side].append(elapsed)
    for side, values in samples.items():
        print(side, dict(median_ms=statistics.median(values), min_ms=min(values), max_ms=max(values)))
    print("paired median saving (ms)", statistics.median(
        before - after for before, after in zip(samples["before"], samples["after"])))


if __name__ == "__main__":
    main()
