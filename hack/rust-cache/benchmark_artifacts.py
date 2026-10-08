#!/usr/bin/env python3
"""Interleave artifact-layout or engine experiments on a captured many-crate workspace."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import statistics
import subprocess
import time


def tree(directory):
    return {str(p.relative_to(directory)): (p.stat().st_mode & 0o777, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in directory.rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-run", type=Path, required=True, help="existing benchmark_scale.py --crates result")
    parser.add_argument("--replay-bin", type=Path, required=True)
    parser.add_argument("--dagger-cli", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--engine", action="append", default=[], metavar="NAME=RUNNER_HOST",
                        help="compare isolated engines using direct compiler snapshots (repeatable)")
    parser.add_argument("--variants", nargs="+",
                        choices=("flat", "balanced64", "balanced16", "balanced64_c8", "directories", "directories_c8", "directories_c32"),
                        help="artifact layouts; defaults to flat, balanced64, directories")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.engine and args.variants:
        parser.error("--engine cannot be combined with --variants")
    engines = {}
    for specification in args.engine:
        name, separator, host = specification.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not host or name in engines:
            parser.error("--engine requires a unique NAME=RUNNER_HOST with a filename-safe name")
        engines[name] = host
    workspace = args.workspace_run.resolve()
    metadata = json.loads((workspace / "summary.json").read_text())
    if not metadata["library_crates"]:
        parser.error("--workspace-run must contain a many-crate workspace")
    source, plan_path = workspace / "source", workspace / "plan.json"
    plan = json.loads(plan_path.read_text())
    output = args.out.resolve()
    if output.is_relative_to(source) or output.is_relative_to(Path.cwd().resolve()):
        parser.error("keep results outside the source and checkout")
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, _EXPERIMENTAL_DAGGER_CLI_BIN=str(args.dagger_cli.resolve()))
    for key in ("DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN"):
        env.pop(key, None)
    env.update(plan["environment"] or {})
    version = subprocess.check_output([str(args.rustc.resolve()), "-Vv"], env=env, text=True).strip()
    if version != plan["rustc_version"].strip():
        parser.error("native rustc differs from the captured toolchain")
    native_env = dict(env, RUSTC=str(args.rustc.resolve()), CARGO_INCREMENTAL="1",
                      CARGO_TARGET_DIR=str(workspace / "cargo_incremental"))
    for key in ("CARGO_BUILD_BUILD_DIR", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        native_env.pop(key, None)
    native = [str(args.cargo.resolve()), "build", "--workspace", "--locked", "--offline", *plan.get("cargo_args", [])]
    available = {"flat": (0, 0, False), "balanced64": (64, 0, False), "balanced16": (16, 0, False),
                 "balanced64_c8": (64, 8, False), "directories": (0, 0, True),
                 "directories_c8": (0, 8, True), "directories_c32": (0, 32, True)}
    variants = ({name: (0, 0, True) for name in engines} if engines else
                {name: available[name] for name in (args.variants or ("flat", "balanced64", "directories"))})
    replay = [str(args.replay_bin.resolve()), "replay", "--source", str(source), "--plan", str(plan_path)]

    def run(command, label, environment=env, cwd=None):
        started = time.monotonic()
        with (output / (label + ".log")).open("w") as log:
            subprocess.run(command, env=environment, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
        return time.monotonic() - started

    def command(variant):
        leaves, concurrency, directories = variants[variant]
        return [*replay, "--artifact-leaf-files", str(leaves), "--compiler-concurrency", str(concurrency),
                *(["--artifact-directories"] if directories else [])]

    def engine_environment(variant):
        return dict(env, _EXPERIMENTAL_DAGGER_RUNNER_HOST=engines[variant]) if engines else env

    def diagnose(variant, label):
        report = output / (label + ".json")
        run([*command(variant), "--out", str(output / (label + "-artifacts")), "--report", str(report)],
            label, engine_environment(variant))
        return {a["id"]: a for a in json.loads(report.read_text())["actions"]}

    def edit(filename, value):
        contents, count = re.subn(r"pub const EDIT: u64 = \d+;", f"pub const EDIT: u64 = {value};", filename.read_text())
        if count != 1:
            raise RuntimeError(f"expected one edit point in {filename}")
        filename.write_text(contents)

    leaf = f"leaf_{metadata['library_crates'] - 1:04d}"
    leaf_file, shared_file = source / leaf / "src/lib.rs", source / "shared/src/lib.rs"
    seed = secrets.randbits(48)
    summary = {"workspace_run": str(workspace), "rustc_version": version,
               "dagger_cli_version": subprocess.check_output([str(args.dagger_cli.resolve()), "version", "--quiet"], env=env, text=True).strip(),
               "variants": {k: {"artifact_leaf_files": v[0], "compiler_concurrency": v[1], "artifact_directories": v[2],
                                **({"runner_host": engines[k]} if engines else {})} for k, v in variants.items()},
               "edit_seed": seed}
    sequence = 0
    for scenario, filename, expected, stdout_index in (
            ("leaf_edited", leaf_file, {leaf, "app"}, 1),
            ("shared_edited", shared_file, {a["crate"] for a in plan["actions"]}, 2)):
        edit(leaf_file, 0)
        edit(shared_file, 0)
        previous = {variant: diagnose(variant, scenario + "-prepare-" + variant) for variant in variants}
        run(native, scenario + "-prepare-cargo", native_env, source)
        rows = []
        names = list(variants)
        for index in range(args.runs):
            order = names[index % len(names):] + names[:index % len(names)]
            for variant in order:
                # Each variant gets a different source edit: identical edits
                # could share compiler results and turn the second run into hits.
                sequence += 1
                value = seed + sequence
                edit(filename, value)
                label = f"{scenario}-{index}-{variant}"
                directory = output / (label + "-artifacts")
                times = {}
                for kind in (("cargo", "replay") if index % 2 == 0 else ("replay", "cargo")):
                    if kind == "cargo":
                        times[kind] = run(native, label + "-cargo", native_env, source)
                    else:
                        times[kind] = run([*command(variant), "--out", str(directory), "--artifacts-only"],
                                          label, engine_environment(variant))
                observed = diagnose(variant, label + "-verify")
                changed = {a["crate"] for key, a in observed.items() if a["execution"] != previous[variant][key]["execution"]}
                if changed != expected:
                    raise RuntimeError(f"{label}: recompiled {sorted(changed)}, expected {sorted(expected)}")
                for key, action in observed.items():
                    if action["execution"] == previous[variant][key]["execution"] and action["digests"] != previous[variant][key]["digests"]:
                        raise RuntimeError("reused operation changed artifact contents")
                if tree(directory) != tree(output / (label + "-verify-artifacts")):
                    raise RuntimeError("measured export differs from verified artifacts")
                binary = next(p for p in (directory / "debug/deps").glob("app-*") if p.is_file() and p.stat().st_mode & 0o111)
                stdout = subprocess.check_output([str(binary)], env=env)
                if stdout != subprocess.check_output([str(workspace / "cargo_incremental/debug/app")], env=env):
                    raise RuntimeError("executable behavior differs from Cargo")
                if stdout.split()[stdout_index] != str(value).encode():
                    raise RuntimeError("executable did not observe the source edit")
                previous[variant] = observed
                rows.append({"variant": variant, "seconds": times, "edit_value": value, "recompiled": sorted(changed)})
                print(label, {k: round(v, 3) for k, v in times.items()}, flush=True)
        medians = {variant: {kind: statistics.median(r["seconds"][kind] for r in rows if r["variant"] == variant)
                             for kind in ("cargo", "replay")} for variant in variants}
        summary[scenario] = {"runs": rows, "median_seconds": medians}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(scenario, medians, flush=True)


if __name__ == "__main__":
    main()
