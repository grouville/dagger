#!/usr/bin/env python3
"""Measure complete replay commands in fresh sessions, optionally against Cargo."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--replay-bin", type=Path, required=True)
    parser.add_argument("--dagger-cli", type=Path, default=os.environ.get("_EXPERIMENTAL_DAGGER_CLI_BIN"),
                        help="matching CLI binary; defaults to _EXPERIMENTAL_DAGGER_CLI_BIN")
    parser.add_argument("--out", type=Path, required=True, help="benchmark logs and results, outside source")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--artifacts-only", action="store_true", help="time artifact export; verify compiler reuse separately afterward")
    parser.add_argument("--cargo", type=Path, help="optional native Cargo binary")
    parser.add_argument("--rustc", type=Path, help="matching native compiler; required with --cargo")
    parser.add_argument("--budget", type=float, default=0.5, help="allowed median replay overhead over native Cargo")
    args = parser.parse_args()
    if args.runs < 1 or args.budget < 0:
        parser.error("--runs must be positive and --budget nonnegative")
    if bool(args.cargo) != bool(args.rustc):
        parser.error("supply both --cargo and --rustc for a native comparison")
    if args.dagger_cli is None:
        parser.error("pin the matching CLI with --dagger-cli or _EXPERIMENTAL_DAGGER_CLI_BIN")
    source, plan_path, executable, output = (p.resolve() for p in (args.source, args.plan, args.replay_bin, args.out))
    if output.is_relative_to(source):
        parser.error("--out must be outside --source")
    plan = json.loads(plan_path.read_text())
    env = dict(os.environ)
    # A benchmark run must not reuse an enclosing SDK's client session.
    for key in ("DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN"):
        env.pop(key, None)
    cli = args.dagger_cli.resolve()
    env["_EXPERIMENTAL_DAGGER_CLI_BIN"] = str(cli)
    try:
        cli_version = subprocess.check_output([str(cli), "version", "--quiet"], text=True, env=env).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        parser.error(f"cannot run the pinned CLI: {error}")
    if args.cargo:
        if "environment" not in plan:
            parser.error("recapture the plan to record its Cargo environment before a native comparison")
        env.update(plan["environment"] or {})
        # Rustup selects cargo/rustc from argv[0]; resolving those symlinks
        # would invoke the rustup manager itself instead of the requested tool.
        compiler = args.rustc.absolute()
        version = subprocess.check_output([str(compiler), "-Vv"], text=True, env=env).strip()
        if version != plan["rustc_version"].strip():
            parser.error("native rustc differs from the captured toolchain; refusing a mismatched comparison")
        cargo = args.cargo.absolute()
        cargo_version = subprocess.check_output([str(cargo), "--version"], text=True, env=env).strip()
        if cargo_version.split()[1] != version.split()[1]:
            parser.error("native Cargo and rustc versions differ")
    output.mkdir(parents=True, exist_ok=True)

    def run(command, label, environment, cwd=None):
        started = time.monotonic()
        with (output / (label + ".log")).open("w") as log:
            subprocess.run(command, env=environment, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
        return time.monotonic() - started

    with tempfile.TemporaryDirectory(prefix="rcexp-bench-") as scratch:
        workspace = Path(scratch) / "source"
        shutil.copytree(source, workspace, symlinks=True, ignore=shutil.ignore_patterns(".git", "target"))

        def replay(label, artifacts_only=False):
            report_path = output / (label + ".json")
            command = [str(executable), "replay", "--source", str(workspace), "--plan", str(plan_path),
                       "--out", str(output / (label + "-artifacts"))]
            command += ["--artifacts-only"] if artifacts_only else ["--report", str(report_path)]
            wall = run(command, label, env)
            result = {"wall_seconds": wall}
            if not artifacts_only:
                result["report"] = json.loads(report_path.read_text())
            return result

        def artifact_tree(label):
            directory = output / (label + "-artifacts")
            return {str(p.relative_to(directory)): (p.stat().st_mode & 0o777, hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in directory.rglob("*") if p.is_file()}

        # Preparation warms images/results. These are warm-cache comparisons,
        # not cold-engine measurements; each measured replay is a new process.
        prepared = replay("prepare")
        actions = {a["id"]: a for a in prepared["report"]["actions"]}
        expected_artifacts = artifact_tree("prepare")
        if args.cargo:
            native_env = dict(env, RUSTC=str(compiler), CARGO_TARGET_DIR=str(Path(scratch) / "native-target"))
            for key in ("CARGO_BUILD_BUILD_DIR", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
                native_env.pop(key, None)
            native_command = [str(cargo), "build", "--workspace", "--locked", "--offline", *plan.get("cargo_args", [])]
            run(native_command, "cargo-prepare", native_env, workspace)
        replay_runs, cargo_runs = [], []
        for index in range(args.runs):
            if args.cargo:
                cargo_runs.append(run(native_command, f"cargo-{index}", native_env, workspace))
            label = f"replay-{index}"
            result = replay(label, args.artifacts_only)
            if artifact_tree(label) != expected_artifacts:
                raise RuntimeError("measured replay exported different artifact contents or permissions")
            if args.artifacts_only:
                # This command is outside the timed interval. Comparing its
                # markers to preparation detects a compiler rerun by either
                # the measured export or this follow-up verification.
                result["verification"] = replay(label + "-verify")
                observed = result["verification"]["report"]["actions"]
            else:
                observed = result["report"]["actions"]
            if len(observed) != len(actions):
                raise RuntimeError("replay changed the number of compiler actions")
            for action in observed:
                previous = actions[action["id"]]
                if action["execution"] != previous["execution"] or action["digests"] != previous["digests"]:
                    raise RuntimeError(f"warm replay did not reuse {action['crate']} unchanged")
            replay_runs.append(result)
            print(f"replay {index + 1}: {result['wall_seconds']:.3f}s, all compiler operations reused", flush=True)

    summary = {"dagger_cli": str(cli), "dagger_cli_version": cli_version,
               "rustc_version": plan["rustc_version"], "preparation": prepared, "replay_runs": replay_runs,
               "replay_median_seconds": statistics.median(r["wall_seconds"] for r in replay_runs),
               "replay_incremental": False, "replay_diagnostics": not args.artifacts_only, "cargo_seconds": cargo_runs}
    if args.cargo:
        summary["cargo_version"] = cargo_version
        summary["cargo_incremental"] = native_env.get("CARGO_INCREMENTAL", "project default")
        summary["cargo_median_seconds"] = statistics.median(cargo_runs)
        summary["overhead_seconds"] = summary["replay_median_seconds"] - summary["cargo_median_seconds"]
        summary["budget_seconds"] = args.budget
        summary["within_budget"] = summary["overhead_seconds"] <= args.budget
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"median replay: {summary['replay_median_seconds']:.3f}s; results: {output / 'summary.json'}")
    if args.cargo:
        print(f"median Cargo: {summary['cargo_median_seconds']:.3f}s; overhead: {summary['overhead_seconds']:.3f}s")
        if not summary["within_budget"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
