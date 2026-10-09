#!/usr/bin/env python3
"""Interleave artifact, source-import or engine experiments on a captured workspace."""

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
    parser.add_argument("--workspace-run", type=Path, required=True, help="existing benchmark_scale.py result")
    parser.add_argument("--replay-bin", type=Path)
    parser.add_argument("--driver", action="append", default=[], metavar="NAME=REPLAY_BIN",
                        help="compare native batch driver implementations on one engine (repeatable)")
    parser.add_argument("--dagger-cli", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--history-warmups", type=int, default=1,
                        help="preparation edits per automatic-history variant; use 4 to measure index expiry")
    parser.add_argument("--engine", action="append", default=[], metavar="NAME=RUNNER_HOST",
                        help="compare isolated engines using direct compiler snapshots (repeatable)")
    parser.add_argument("--variants", nargs="+",
                        choices=("flat", "balanced64", "balanced16", "balanced64_c8", "directories", "directories_c8", "directories_c32", "directories_native", "directories_auto", "directories_native_auto", "native_auto_batch", "native_auto_batch_no_pipeline"),
                        help="artifact layouts; defaults to flat, balanced64, directories")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if args.history_warmups < 1:
        parser.error("--history-warmups must be positive")
    if args.engine and args.variants:
        parser.error("--engine cannot be combined with --variants")
    if args.driver and (args.engine or args.variants or args.replay_bin):
        parser.error("--driver cannot be combined with --engine, --variants or --replay-bin")
    if not args.driver and args.replay_bin is None:
        parser.error("provide --replay-bin or --driver")
    drivers = {}
    for specification in args.driver:
        name, separator, filename = specification.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not filename or name in drivers:
            parser.error("--driver requires a unique NAME=REPLAY_BIN with a filename-safe name")
        driver = Path(filename).resolve()
        if not driver.is_file():
            parser.error(f"driver does not exist: {driver}")
        drivers[name] = driver
    engines = {}
    for specification in args.engine:
        name, separator, host = specification.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not host or name in engines:
            parser.error("--engine requires a unique NAME=RUNNER_HOST with a filename-safe name")
        engines[name] = host
    workspace = args.workspace_run.resolve()
    metadata = json.loads((workspace / "summary.json").read_text())
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
    def settings(leaves=0, concurrency=0, directories=False, native_sources=False, automatic=False, batch=False, no_pipelining=False):
        return {"artifact_leaf_files": leaves, "compiler_concurrency": concurrency,
                "artifact_directories": directories, "native_sources": native_sources,
                "automatic_incremental": automatic, "batch": batch, "batch_no_pipelining": no_pipelining}

    available = {"flat": settings(), "balanced64": settings(leaves=64), "balanced16": settings(leaves=16),
                 "balanced64_c8": settings(leaves=64, concurrency=8), "directories": settings(directories=True),
                 "directories_c8": settings(directories=True, concurrency=8),
                 "directories_c32": settings(directories=True, concurrency=32),
                 "directories_native": settings(directories=True, native_sources=True),
                 "directories_auto": settings(directories=True, automatic=True),
                 "directories_native_auto": settings(directories=True, native_sources=True, automatic=True),
                 "native_auto_batch": settings(directories=True, native_sources=True, automatic=True, batch=True),
                 "native_auto_batch_no_pipeline": settings(directories=True, native_sources=True, automatic=True, batch=True, no_pipelining=True)}
    variants = ({name: available["native_auto_batch"] for name in drivers} if drivers else
                {name: settings(directories=True) for name in engines} if engines else
                {name: available[name] for name in (args.variants or ("flat", "balanced64", "directories"))})

    def run(command, label, environment=env, cwd=None):
        started = time.monotonic()
        with (output / (label + ".log")).open("w") as log:
            subprocess.run(command, env=environment, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
        return time.monotonic() - started

    def command(variant):
        options = variants[variant]
        driver = drivers[variant] if drivers else args.replay_bin.resolve()
        replay = [str(driver), "replay", "--source", str(source), "--plan", str(plan_path)]
        return [*replay, "--artifact-leaf-files", str(options["artifact_leaf_files"]),
                "--compiler-concurrency", str(options["compiler_concurrency"]),
                *(["--artifact-directories"] if options["artifact_directories"] else []),
                *(["--native-sources"] if options["native_sources"] else []),
                *(["--batch"] if options["batch"] else []),
                *(["--batch-no-pipelining"] if options["batch_no_pipelining"] else []),
                *(["--auto-incremental", str(output / (variant + "-history.json"))] if options["automatic_incremental"] else [])]

    def engine_environment(variant):
        return dict(env, _EXPERIMENTAL_DAGGER_RUNNER_HOST=engines[variant]) if engines else env

    def diagnose(variant, label, expect_finished_hits=False):
        report = output / (label + ".json")
        run([*command(variant), "--out", str(output / (label + "-artifacts")), "--report", str(report)],
            label, engine_environment(variant))
        if expect_finished_hits and variants[variant]["automatic_incremental"]:
            hits = re.findall(r"native history reused (\d+)/(\d+) compiler results",
                              (output / (label + ".log")).read_text())
            expected_hits = (str(len(plan["actions"])), str(len(plan["actions"])))
            if not hits or hits[-1] != expected_hits:
                raise RuntimeError(f"{label}: validation did not reuse every finished result: {hits}")
        return {a["id"]: a for a in json.loads(report.read_text())["actions"]}

    def edit(filename, value):
        contents, count = re.subn(r"pub const EDIT: u64 = \d+;", f"pub const EDIT: u64 = {value};", filename.read_text())
        if count != 1:
            raise RuntimeError(f"expected one edit point in {filename}")
        filename.write_text(contents)

    if metadata["library_crates"]:
        leaf = f"leaf_{metadata['library_crates'] - 1:04d}"
        leaf_file, shared_file = source / leaf / "src/lib.rs", source / "shared/src/lib.rs"
        scenarios = (("leaf_edited", leaf_file, {leaf, "app"}, 1),
                     ("shared_edited", shared_file, {a["crate"] for a in plan["actions"]}, 2))
    else:
        scenarios = (("edited", source / "app/src/part_0000.rs", {"app"}, 1),)
    seed = secrets.randbits(48)
    summary = {"workspace_run": str(workspace), "rustc_version": version,
               "dagger_cli_version": subprocess.check_output([str(args.dagger_cli.resolve()), "version", "--quiet"], env=env, text=True).strip(),
               "variants": {k: {**v,
                                **({"runner_host": engines[k]} if engines else {}),
                                **({"replay_bin": str(drivers[k])} if drivers else {})} for k, v in variants.items()},
               "edit_seed": seed, "history_warmups": args.history_warmups}
    sequence = 0
    for scenario, filename, expected, stdout_index in scenarios:
        for _, editable, _, _ in scenarios:
            edit(editable, 0)
        previous = {}
        for variant in variants:
            warmups = args.history_warmups if variants[variant]["automatic_incremental"] else 1
            for index in range(warmups):
                if warmups > 1:
                    sequence += 1
                    edit(filename, seed + sequence)
                previous[variant] = diagnose(variant, f"{scenario}-prepare-{variant}-{index}")
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
                observed = diagnose(variant, label + "-verify", expect_finished_hits=True)
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
