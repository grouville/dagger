#!/usr/bin/env python3
"""Compare the real Go discovery UX in alternating, fresh CLI processes.

Use disposable fixtures from bench-artifact-discovery-fixture.py --go-module.
Build binaries and warm toolchains before running this unprofiled matrix.
Run the invalidation runner separately for edit correctness and wcprof separately
for attribution. All commands below list metadata/keys; they do not run checks.
"""

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys


SURFACES = {
    "overview": ["list"],
    "default-checks": ["check", "-l"],
    "collection-modules": ["list", "go-modules"],
    "collection-tests": ["list", "go-tests"],
    "artifact-checks": ["list", "checks", "go/modules/tests/run"],
    "all-artifacts": ["list", "-a"],
    "expanded-checks": ["check", "-l", "--all", "--generated=false", "go/modules/tests/run"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for variant in ("baseline", "candidate"):
        parser.add_argument(f"--{variant}-cli", type=Path, required=True)
        parser.add_argument(f"--{variant}-workspace", type=Path, required=True)
        parser.add_argument(f"--{variant}-engine", required=True)
    parser.add_argument("--surface", action="append", choices=SURFACES,
                        help="repeat to select commands; defaults to all seven")
    parser.add_argument("--runs", type=int, default=5, help="pairs per command")
    parser.add_argument("--warmups", type=int, default=1, help="per variant and command, before its first pair")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-ms", type=float, help="fail if any candidate sample exceeds this budget")
    args = parser.parse_args()
    if args.runs <= 0 or args.warmups < 0 or (args.budget_ms is not None and args.budget_ms <= 0):
        parser.error("runs/budget must be positive and warmups nonnegative")
    if args.output.exists():
        parser.error("output must be a new directory, to preserve earlier evidence")
    args.output.mkdir(parents=True)
    runner = Path(__file__).with_name("bench-artifact-discovery.py")
    samples, medians = [], {}
    over_budget = []
    for surface in dict.fromkeys(args.surface or SURFACES):
        hashes = set()
        for repetition in range(args.runs):
            order = ("baseline", "candidate") if repetition % 2 == 0 else ("candidate", "baseline")
            for variant in order:
                dest = args.output / surface / f"{variant}-{repetition}"
                command = [
                    str(getattr(args, f"{variant}_cli").resolve()),
                    "--engine", getattr(args, f"{variant}_engine"),
                    "--workspace", str(getattr(args, f"{variant}_workspace").resolve()),
                    *SURFACES[surface],
                ]
                subprocess.run([
                    sys.executable, str(runner), "--runs", "1",
                    "--warmups", str(args.warmups if repetition == 0 else 0),
                    "--output", str(dest), "--", *command,
                ], check=True, stdout=subprocess.DEVNULL)
                result = json.loads((dest / "results.json").read_text())
                sample = {"surface": surface, "variant": variant, "repetition": repetition,
                          "seconds": result["median_seconds"],
                          "stdout_sha256": result["runs"][0]["stdout_sha256"]}
                samples.append(sample)
                hashes.add(sample["stdout_sha256"])
                print(json.dumps(sample), flush=True)
                if variant == "candidate" and args.budget_ms is not None and sample["seconds"] * 1000 > args.budget_ms:
                    over_budget.append({"surface": surface, "repetition": repetition})
        medians[surface] = {
            variant: statistics.median(s["seconds"] for s in samples
                                       if s["surface"] == surface and s["variant"] == variant)
            for variant in ("baseline", "candidate")
        }
        summary = {"medians": medians, "runs": samples,
                   "budget_ms": args.budget_ms, "over_budget": over_budget}
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        if len(hashes) != 1:
            raise SystemExit(f"{surface}: outputs differ; inspect saved stdout before accepting timings")
    if over_budget:
        raise SystemExit(f"{len(over_budget)} candidate samples exceeded {args.budget_ms:g} ms; see summary.json")


if __name__ == "__main__":
    main()
