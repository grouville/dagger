#!/usr/bin/env python3
"""Compare fresh crate edits with Cargo and optional native incremental snapshots."""

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
    return [("edited", source / "app/src/part_0000.rs", {"app"}, 1)]


def generate_workspace(source, crates, shape, codegen_units, library_functions=0):
    """Separate one-crate invalidation from shared-dependency invalidation."""
    source.mkdir()
    names = [f"leaf_{index:04d}" for index in range(crates)]
    members = ["shared", *names, "app"]
    (source / "Cargo.toml").write_text(
        "[workspace]\nmembers = " + json.dumps(members) +
        f'\nresolver = "2"\n\n[profile.dev]\ncodegen-units = {codegen_units}\n')

    def package(name, dependencies, code, binary=False):
        root = source / name
        (root / "src").mkdir(parents=True)
        manifest = f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
        manifest += "".join(f'{dep} = {{ path = "../{dep}" }}\n' for dep in dependencies)
        (root / "Cargo.toml").write_text(manifest)
        if not binary:
            # Exported functions force substantial library code generation
            # without changing the edit checks in the application.
            for function in range(library_functions):
                salt = function + 1
                code += f"""\n#[inline(never)]
pub fn compute_{function}(seed: u64) -> u64 {{
    let mut values = [seed.wrapping_add({salt}); 16];
    for (index, value) in values.iter_mut().enumerate() {{
        *value = value.rotate_left(index as u32).wrapping_mul({salt * 2 + 1});
    }}
    values.iter().fold(0, |sum, value| sum ^ value)
}}
"""
        (root / "src" / ("main.rs" if binary else "lib.rs")).write_text(code)

    package("shared", [], "pub const EDIT: u64 = 0;\npub fn value() -> u64 { EDIT }\n")
    for index, name in enumerate(names):
        dependency = names[index - 1] if shape == "chain" and index else "shared"
        package(name, [dependency], "pub const EDIT: u64 = 0;\n" +
                f"pub fn value() -> u64 {{ {dependency}::value().wrapping_add({index + 1}).wrapping_add(EDIT) }}\n")
    leaves = names[-1:] if shape == "chain" else names
    edited_leaf = leaves[-1]
    expression = "0u64" + "".join(f".wrapping_add({name}::value())" for name in leaves)
    package("app", ["shared", *leaves],
            f'fn main() {{ println!("{{}} {{}} {{}}", {expression}, {edited_leaf}::EDIT, shared::EDIT); }}\n', binary=True)
    return [("leaf_edited", source / edited_leaf / "src/lib.rs", {edited_leaf, "app"}, 1),
            ("shared_edited", source / "shared/src/lib.rs", set(members), 2)]


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
    parser.add_argument("--incremental", action="store_true", help="also measure explicit native incremental seeds for the application")
    parser.add_argument("--crates", type=int, default=0, help="generate this many library crates instead of one large application")
    parser.add_argument("--library-functions", type=int, default=0, help="export this many additional functions per generated library for code-generation overlap experiments")
    parser.add_argument("--shape", choices=("fanout", "chain"), default="fanout")
    parser.add_argument("--artifact-leaf-files", type=int, default=0)
    parser.add_argument("--artifact-directories", action="store_true")
    parser.add_argument("--native-sources", action="store_true")
    parser.add_argument("--compiler-concurrency", type=int, default=0)
    args = parser.parse_args()
    if min(args.runs, args.modules, args.functions, args.codegen_units) < 1:
        parser.error("--runs, --modules, --functions and --codegen-units must be positive")
    if args.crates < 0 or args.library_functions < 0:
        parser.error("--crates and --library-functions must be nonnegative")
    if args.library_functions and not args.crates:
        parser.error("--library-functions requires --crates")
    if args.artifact_leaf_files < 0 or args.compiler_concurrency < 0:
        parser.error("--artifact-leaf-files and --compiler-concurrency must be nonnegative")
    output = args.out.resolve()
    if output.is_relative_to(Path.cwd().resolve()):
        parser.error("keep generated workspaces and results outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    if args.crates:
        scenarios = generate_workspace(source, args.crates, args.shape, args.codegen_units, args.library_functions)
    else:
        scenarios = generate(source, args.modules, args.functions, args.codegen_units)
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
    if args.crates:
        run([str(cargo), "generate-lockfile", "--offline"], "lockfile", dict(env, RUSTC=str(compiler)), source)
    run([executable, "capture", "--source", str(source), "--plan", str(plan_path)], "capture")
    plan = json.loads(plan_path.read_text())
    if compiler_version != plan["rustc_version"].strip():
        parser.error("native rustc differs from the captured toolchain")
    env.update(plan["environment"] or {})
    replay = [executable, "replay", "--source", str(source), "--plan", str(plan_path)]
    replay += ["--artifact-leaf-files", str(args.artifact_leaf_files), "--compiler-concurrency", str(args.compiler_concurrency)]
    if args.artifact_directories:
        replay += ["--artifact-directories"]
    if args.native_sources:
        replay += ["--native-sources"]

    def diagnose(label, extra=()):
        report = output / (label + ".json")
        run([*replay, *extra, "--out", str(output / (label + "-artifacts")), "--report", str(report)], label)
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
    def verify(observed, previous, expected, directory, verified):
        if observed.keys() != previous.keys():
            raise RuntimeError("compiler action set changed")
        changed = []
        for action_id, action in observed.items():
            old = previous[action_id]
            if action["execution"] != old["execution"]:
                changed.append(action["crate"])
            elif action["digests"] != old["digests"]:
                raise RuntimeError("reused operation changed artifact contents")
        if set(changed) != expected:
            raise RuntimeError(f"unexpected compiler executions: {changed}, expected {sorted(expected)}")
        if tree(directory) != tree(verified):
            raise RuntimeError("measured export differs from verified artifacts")
        return changed

    state = output / "prepare-state.json"
    previous_seeded = None
    if args.incremental:
        previous_seeded = diagnose("prepare-seeded", ["--incremental-crate", "app", "--state", str(state)])
    # Reusing deterministic edit values on the same engine can measure old
    # compiler results instead of fresh misses. Keep this run's values unique.
    edit_seed = secrets.randbits(48)
    summary = {"dagger_cli_version": cli_version, "rustc_version": compiler_version, "cargo_version": cargo_version,
               "modules": args.modules, "functions_per_module": args.functions, "codegen_units": args.codegen_units,
               "library_crates": args.crates, "shape": args.shape if args.crates else None,
               "library_functions": args.library_functions,
               "artifact_leaf_files": args.artifact_leaf_files, "compiler_concurrency": args.compiler_concurrency,
               "artifact_directories": args.artifact_directories,
               "native_sources": args.native_sources,
               "edit_seed": edit_seed,
               "cargo_incremental": {"cargo_incremental": True, "cargo_full": False},
               "replay_incremental": False, "replay_seeded_incremental_crates": ["app"] if args.incremental else []}
    kinds = ["cargo_incremental", "cargo_full", "replay"]
    if args.incremental:
        kinds.append("replay_seeded")
    for scenario, edits, expected_changed, stdout_index in scenarios:
        original = edits.read_text()
        rows = []
        for index in range(args.runs):
            edit_value = edit_seed + index + 1
            edits.write_text(original.replace("pub const EDIT: u64 = 0;", f"pub const EDIT: u64 = {edit_value};"))
            times = {}
            label = f"{scenario}-{index}"
            directory = output / (label + "-artifacts")
            seeded_directory = output / (label + "-seeded-artifacts")
            next_state = output / (label + "-state.json")
            seed_args = ["--incremental-crate", "app", "--seed", str(state)]
            order = kinds[index % len(kinds):] + kinds[:index % len(kinds)]
            for kind in order:
                if kind == "replay":
                    times[kind] = run([*replay, "--out", str(directory), "--artifacts-only"], label + "-" + kind)
                elif kind == "replay_seeded":
                    times[kind] = run([*replay, *seed_args, "--state", str(next_state),
                                       "--out", str(seeded_directory), "--artifacts-only"], label + "-" + kind)
                else:
                    times[kind] = run(native_command, label + "-" + kind, environments[kind], source)
            # Verification is outside all measured commands. It detects both
            # accidental recompilation and missed invalidation.
            observed = diagnose(label + "-verify")
            changed = verify(observed, previous, expected_changed, directory, output / (label + "-verify-artifacts"))
            seeded_changed = None
            if args.incremental:
                seeded_label = label + "-seeded-verify"
                seeded = diagnose(seeded_label, [*seed_args, "--state", str(output / (seeded_label + "-state.json"))])
                seeded_changed = verify(seeded, previous_seeded, expected_changed, seeded_directory,
                                        output / (seeded_label + "-artifacts"))
                previous_seeded = seeded
                state = next_state
            app = next(p for p in (directory / "debug/deps").glob("app-*") if p.is_file() and p.stat().st_mode & 0o111)
            stdout = subprocess.check_output([str(app)], env=env)
            for kind in environments:
                if subprocess.check_output([str(output / kind / "debug/app")], env=env) != stdout:
                    raise RuntimeError(f"replay executable behavior differs from {kind}")
            if args.incremental:
                seeded_app = next(p for p in (seeded_directory / "debug/deps").glob("app-*") if p.is_file() and p.stat().st_mode & 0o111)
                if subprocess.check_output([str(seeded_app)], env=env) != stdout:
                    raise RuntimeError("seeded executable behavior differs from full replay")
            if stdout.split()[stdout_index] != str(edit_value).encode():
                raise RuntimeError("executable did not observe the source edit")
            previous = observed
            rows.append({"seconds": times, "recompiled": changed, "seeded_recompiled": seeded_changed,
                         "stdout": stdout.decode(), "edit_value": edit_value})
            print(scenario, index + 1, {kind: round(value, 3) for kind, value in times.items()}, flush=True)
        medians = {kind: statistics.median(r["seconds"][kind] for r in rows) for kind in kinds}
        summary[scenario] = {"runs": rows, "median_seconds": medians,
                             "overhead_seconds": medians["replay"] - medians["cargo_incremental"],
                             "overhead_without_incremental_seconds": medians["replay"] - medians["cargo_full"]}
        if args.incremental:
            summary[scenario]["seeded_overhead_seconds"] = medians["replay_seeded"] - medians["cargo_incremental"]
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(scenario, medians, flush=True)


if __name__ == "__main__":
    main()
