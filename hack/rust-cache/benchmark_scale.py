#!/usr/bin/env python3
"""Compare unchanged and edited multi-file crates with Cargo's incremental control."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import statistics
import subprocess
import time


def generate(source, modules, functions, codegen_units):
    fixture = Path(__file__).parent / "replay/testdata/workspace"
    shutil.copytree(fixture, source)
    # Cargo's defaults also change codegen units with incremental compilation.
    # Keep that compiler setting equal to isolate incremental-state reuse.
    with (source / "Cargo.toml").open("a") as manifest:
        manifest.write(f"\n[profile.dev]\ncodegen-units = {codegen_units}\n")
    main = []
    for module in range(modules):
        name = f"part_{module:04d}"
        main.append(f"mod {name};")
        lines = ["pub const EDIT: u64 = 0;"]
        for function in range(functions):
            salt = module * functions + function + 1
            lines.append(f"""fn f_{function}(seed: u64) -> u64 {{
    let mut values = [seed.wrapping_add({salt}); 16];
    for (index, value) in values.iter_mut().enumerate() {{
        *value = value.rotate_left(index as u32).wrapping_mul({salt * 2 + 1});
    }}
    values.iter().fold(0, |sum, value| sum ^ value)
}}""")
        expression = "0u64" + "".join(f".wrapping_add(f_{function}(seed))" for function in range(functions))
        lines.append(f"pub fn compute(seed: u64) -> u64 {{ {expression}.wrapping_add(EDIT) }}")
        (source / f"app/src/{name}.rs").write_text("\n".join(lines) + "\n")
    main += ["fn main() {", "    let seed = u64::from(left::value() + right::value());", "    let mut total = 0u64;"]
    main += [f"    total = total.wrapping_add(part_{module:04d}::compute(seed));" for module in range(modules)]
    main += ['    println!("{} {} {}", total, part_0000::EDIT, right::label());', "}"]
    (source / "app/src/main.rs").write_text("\n".join(main) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-bin", type=Path, required=True)
    parser.add_argument("--dagger-cli", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="new result directory outside the workspace")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--modules", type=int, default=128)
    parser.add_argument("--functions", type=int, default=8)
    parser.add_argument("--codegen-units", type=int, default=16, help="same codegen unit count for all three builds")
    args = parser.parse_args()
    if min(args.runs, args.modules, args.functions, args.codegen_units) < 1:
        parser.error("--runs, --modules, --functions and --codegen-units must be positive")
    output = args.out.resolve()
    if output.is_relative_to(Path.cwd().resolve()):
        parser.error("keep generated workspaces and results outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    generate(source, args.modules, args.functions, args.codegen_units)
    env = dict(os.environ, _EXPERIMENTAL_DAGGER_CLI_BIN=str(args.dagger_cli.resolve()))
    for key in ("DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN"):
        env.pop(key, None)
    cli_version = subprocess.check_output([str(args.dagger_cli.resolve()), "version", "--quiet"], env=env, text=True).strip()
    compiler, cargo = args.rustc.absolute(), args.cargo.absolute()
    compiler_version = subprocess.check_output([str(compiler), "-Vv"], env=env, text=True).strip()
    cargo_version = subprocess.check_output([str(cargo), "--version"], env=env, text=True).strip()
    if cargo_version.split()[1] != compiler_version.split()[1]:
        parser.error("native Cargo and rustc versions differ")

    def run(command, label, environment=env, cwd=None):
        start = time.monotonic()
        with (output / (label + ".log")).open("w") as log:
            subprocess.run(command, env=environment, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)
        return time.monotonic() - start

    executable = str(args.replay_bin.resolve())
    plan_path = output / "plan.json"
    run([executable, "capture", "--source", str(source), "--plan", str(plan_path)], "capture")
    plan = json.loads(plan_path.read_text())
    if compiler_version != plan["rustc_version"].strip():
        parser.error("native rustc differs from the captured toolchain")
    env.update(plan["environment"] or {})
    replay = [executable, "replay", "--source", str(source), "--plan", str(plan_path)]

    def diagnose(label):
        report = output / (label + ".json")
        run([*replay, "--out", str(output / (label + "-artifacts")), "--report", str(report)], label)
        return {a["id"]: a for a in json.loads(report.read_text())["actions"]}

    def tree(directory):
        return {str(p.relative_to(directory)): (p.stat().st_mode & 0o777, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in directory.rglob("*") if p.is_file()}

    native_command = [str(cargo), "build", "--workspace", "--locked", "--offline", *plan.get("cargo_args", [])]
    environments = {}
    for label, incremental in (("cargo_incremental", "1"), ("cargo_full", "0")):
        native = dict(env, RUSTC=str(compiler), CARGO_INCREMENTAL=incremental, CARGO_TARGET_DIR=str(output / label))
        for key in ("CARGO_BUILD_BUILD_DIR", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
            native.pop(key, None)
        environments[label] = native
        run(native_command, label + "-prepare", native, source)
    previous = diagnose("prepare")
    captured = {path: digest for action in previous.values() for path, digest in action["digests"].items()}
    if captured != plan["baseline_digests"]:
        raise RuntimeError("initial replay differs from captured Cargo artifacts")
    expected_tree = tree(output / "prepare-artifacts")
    edits = source / "app/src/part_0000.rs"
    original = edits.read_text()
    # Reusing deterministic edit values on the same engine can measure old
    # compiler results instead of fresh misses. Keep this run's values unique.
    edit_seed = secrets.randbits(48)
    summary = {"dagger_cli_version": cli_version, "rustc_version": compiler_version, "cargo_version": cargo_version,
               "modules": args.modules, "functions_per_module": args.functions, "codegen_units": args.codegen_units,
               "edit_seed": edit_seed,
               "cargo_incremental": {"cargo_incremental": True, "cargo_full": False}, "replay_incremental": False}
    kinds = ["cargo_incremental", "cargo_full", "replay"]
    for scenario in ("unchanged", "edited"):
        rows = []
        for index in range(args.runs):
            edit_value = edit_seed + index + 1 if scenario == "edited" else 0
            if scenario == "edited":
                edits.write_text(original.replace("pub const EDIT: u64 = 0;", f"pub const EDIT: u64 = {edit_value};"))
            times = {}
            label = f"{scenario}-{index}"
            directory = output / (label + "-artifacts")
            order = kinds[index % len(kinds):] + kinds[:index % len(kinds)]
            for kind in order:
                if kind == "replay":
                    times[kind] = run([*replay, "--out", str(directory), "--artifacts-only"], label + "-" + kind)
                else:
                    times[kind] = run(native_command, label + "-" + kind, environments[kind], source)
            if scenario == "unchanged" and tree(directory) != expected_tree:
                raise RuntimeError("unchanged export contents or permissions differ")
            # Verification is outside all measured commands. It detects both
            # accidental recompilation and missed invalidation.
            observed = diagnose(label + "-verify")
            if observed.keys() != previous.keys():
                raise RuntimeError("compiler action set changed")
            changed = []
            for action_id, action in observed.items():
                old = previous[action_id]
                if action["execution"] != old["execution"]:
                    changed.append(action["crate"])
                elif action["digests"] != old["digests"]:
                    raise RuntimeError("reused operation changed artifact contents")
            if sorted(changed) != (["app"] if scenario == "edited" else []):
                raise RuntimeError(f"unexpected compiler executions: {changed}")
            if tree(directory) != tree(output / (label + "-verify-artifacts")):
                raise RuntimeError("measured export differs from verified artifacts")
            app = next(p for p in (directory / "debug/deps").glob("app-*") if p.is_file() and p.stat().st_mode & 0o111)
            stdout = subprocess.check_output([str(app)], env=env)
            for kind in environments:
                if subprocess.check_output([str(output / kind / "debug/app")], env=env) != stdout:
                    raise RuntimeError(f"replay executable behavior differs from {kind}")
            if stdout.split()[1] != str(edit_value).encode():
                raise RuntimeError("executable did not observe the source edit")
            previous = observed
            rows.append({"seconds": times, "recompiled": changed, "stdout": stdout.decode()})
            print(scenario, index + 1, {kind: round(value, 3) for kind, value in times.items()}, flush=True)
        medians = {kind: statistics.median(r["seconds"][kind] for r in rows) for kind in kinds}
        summary[scenario] = {"runs": rows, "median_seconds": medians,
                             "overhead_seconds": medians["replay"] - medians["cargo_incremental"],
                             "overhead_without_incremental_seconds": medians["replay"] - medians["cargo_full"]}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(scenario, medians, flush=True)


if __name__ == "__main__":
    main()
