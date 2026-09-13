#!/usr/bin/env python3
"""Compare CLI variants on alternating, novel edits in owned run.py copies.

Requires --execute and an explicit DAGGER_ENGINE targeting the same running
engine for both sides. Mutates ONLY the two run.py benchmark source copies;
original bytes and all results are retained in a new temporary directory.
Sources stay edited on success or failure. No cache resets, Docker changes,
resident sessions, native Cargo timings, or cold-performance claim.

Each scenario has one excluded warmup pair followed by --samples measured
pairs. Only standalone `dagger check rust:check` enters timings.csv. Diagnostic
`api call rust check-log` runs afterwards, outside both checks' timers. Its
cached Cargo output is NOT independent proof of execution: audit OTel as well.
"""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time
import tomllib
import uuid


REVISION = "3fce3b5bb0236da2df6d99672afb8a719642eca7"
PATHS = {"application": "crates/core/flags/doc/version.rs",
         "workspace-library": "crates/printer/src/standard.rs"}
PATTERNS = {
    "application": rb'format!\("ripgrep \{digits\}(?: bench-[A-Za-z0-9_-]+)?"\)',
    # There are TWO omitted-context literals. Select one unique output branch.
    "workspace-library": (
        rb'(if self\.sunk\.original_matches\(\)\.is_empty\(\) \{\s+'
        rb'if self\.is_context\(\) \{\s+self\.write\(b")'
        rb'\[Omitted long context line(?: bench-[A-Za-z0-9_-]+)?\]("\)\?;)'),
}
EXPECTED = {"application": {"ripgrep"},
            "workspace-library": {"grep-printer", "grep", "ripgrep"}}
WORKLOAD_KEYS = ("image", "shell_phase_instrumentation", "source_sync_delivery",
                 "prepare_project_toolchain", "project_toolchain_sha256",
                 "dependency_upgrade")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def source_hashes(workdir):
    hashes = {}
    for directory, dirs, files in os.walk(workdir):
        dirs[:] = sorted(name for name in dirs if name not in {".git", "target"})
        for name in dirs + sorted(files):
            path = Path(directory) / name
            require(not path.is_symlink(), f"fixture source symlink: {path}")
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(workdir).as_posix()
            if relative not in {"dagger.toml", "dagger.lock"}:
                hashes[relative] = digest(path)
    return hashes


def validate_side(workdir, cli_hash):
    require(workdir.name == "dagger" and workdir.parent.name.startswith("dagger-rust-loop-"),
            f"not a run.py-owned dagger workspace: {workdir}")
    require((workdir / ".git").is_dir() and (workdir.parent / "native/Cargo.toml").is_file(),
            f"missing run.py fixture layout: {workdir}")
    metadata = json.loads((workdir.parent / "metadata.json").read_text())
    require(metadata.get("fixture") == "ripgrep" and metadata.get("fixture_revision") == REVISION,
            f"not the pinned ripgrep fixture: {workdir}")
    require(metadata.get("cli_sha256") == cli_hash, f"CLI differs from recorded fixture: {workdir}")
    require(re.fullmatch(r".+@sha256:[0-9a-f]{64}", metadata["image"]),
            f"image is not digest-pinned: {workdir}")
    for key in WORKLOAD_KEYS:
        require(key in metadata, f"missing recorded workload setting {key}: {workdir}")
    module = Path(metadata["module_dir"]).resolve(strict=True)
    for filename, key in (("main.dang", "module_sha256"),
                          ("dagger-module.toml", "module_config_sha256")):
        require(digest(module / filename) == metadata.get(key),
                f"module variant changed since run.py: {module / filename}")
    config = tomllib.loads((workdir / "dagger.toml").read_text())
    require(set(config) == {"modules"} and set(config["modules"]) == {"rust"},
            f"unexpected Dagger configuration: {workdir}")
    rust = config["modules"]["rust"]
    require(set(rust) == {"source", "settings"} and Path(rust["source"]).resolve() == module,
            f"module source differs from recorded fixture: {workdir}")
    settings = rust["settings"]
    expected = {"image": metadata["image"], "cacheKey": "rust-loop-" + workdir.parent.name}
    for setting, enabled in (
        ("tracePhases", metadata["shell_phase_instrumentation"]),
        ("pinnedSourceSync", metadata["source_sync_delivery"] == "pinned-debian-packages"),
        ("prepareProjectToolchain", metadata["prepare_project_toolchain"]),
    ):
        if enabled:
            expected[setting] = True
    require(settings == expected, f"settings differ from recorded run.py workload: {workdir}")
    toolchain = workdir / "rust-toolchain.toml"
    require((digest(toolchain) if toolchain.exists() else None) == metadata["project_toolchain_sha256"],
            f"root toolchain differs from recorded fixture: {workdir}")
    for relative, name, version in (("Cargo.toml", "ripgrep", "15.2.0"),
                                    ("crates/printer/Cargo.toml", "grep-printer", "0.3.1"),
                                    ("crates/grep/Cargo.toml", "grep", "0.4.1")):
        package = tomllib.loads((workdir / relative).read_text())["package"]
        require((package["name"], package["version"]) == (name, version),
                f"unexpected fixture package: {workdir / relative}")
    originals = {}
    for scenario, relative in PATHS.items():
        path = workdir / relative
        require(path.resolve() == path and path.stat().st_nlink == 1,
                f"edit target must not be a symlink or hard link: {path}")
        originals[scenario] = path.read_bytes()
        require(len(re.findall(PATTERNS[scenario], originals[scenario])) == 1,
                f"expected exactly one {scenario} edit anchor: {path}")
    return metadata, originals, source_hashes(workdir)


def edited(original, scenario, token):
    token = token.encode("ascii")
    if scenario == "application":
        replacement = lambda _: b'format!("ripgrep {digits} bench-' + token + b'")'
    else:
        replacement = lambda match: (match[1] + b"[Omitted long context line bench-" + token
                                     + b"]" + match[2])
    result, count = re.subn(PATTERNS[scenario], replacement, original)
    require(count == 1 and result != original, f"invalid {scenario} edit")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dagger", required=True, type=Path, help="Control CLI also used for both fixture primers")
    parser.add_argument("--after-dagger", required=True, type=Path)
    parser.add_argument("--profile", action="store_true", help="Separate diagnostic cohort, not headline timing")
    parser.add_argument("--before-workdir", required=True, type=Path)
    parser.add_argument("--after-workdir", required=True, type=Path)
    parser.add_argument("--samples", default=10, type=int)
    parser.add_argument("--execute", action="store_true", help="Allow edits to the owned fixture copies")
    args = parser.parse_args()
    env = os.environ.copy()
    try:
        require(args.execute, "pass --execute to allow benchmark-copy mutations")
        require(args.samples > 0, "--samples must be positive")
        require(env.get("DAGGER_ENGINE"), "set DAGGER_ENGINE explicitly for this same-engine comparison")
        require(not any(key.startswith("_EXPERIMENTAL_DAGGER_") or key in
                        {"DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN"} for key in env),
                "remove experimental overrides and nested-session variables; ordinary CLI caching is required")
        dagger = args.dagger.resolve(strict=True)
        cli_hash = digest(dagger)
        binaries = {"before": dagger, "after": args.after_dagger.resolve(strict=True)}
        binary_hashes = {side: digest(path) for side, path in binaries.items()}
        workdirs = {"before": args.before_workdir.resolve(strict=True),
                    "after": args.after_workdir.resolve(strict=True)}
        require(not workdirs["before"].samefile(workdirs["after"]), "workspaces must be distinct")
        require(not any(args_path.absolute() != workdirs[side] for side, args_path in
                        (("before", args.before_workdir), ("after", args.after_workdir))),
                "use canonical workspace paths without symlinks")
        validated = {side: validate_side(path, cli_hash) for side, path in workdirs.items()}
        before, after = (validated[side] for side in workdirs)
        require(before[1] == after[1] and before[2] == after[2], "fixture source trees must be identical")
        require(all(before[0][key] == after[0][key] for key in WORKLOAD_KEYS),
                "fixture workload settings differ")
        require(before[0].get("engine_image_id") == after[0].get("engine_image_id"),
                "recorded engine image identities differ")
    except (ValueError, KeyError, OSError) as error:
        parser.error(str(error))

    root = Path(tempfile.mkdtemp(prefix="dagger-rust-module-edits-"))
    print(root, flush=True)
    nonce = uuid.uuid4().hex
    metadata = {
        "purpose": "alternating novel edits comparing two CLIs; both fixtures primed with control; not native Cargo or cold performance",
        "binaries": {side: str(path) for side, path in binaries.items()}, "binary_sha256": binary_hashes,
        "script_sha256": digest(Path(__file__)), "cli": str(dagger), "cli_sha256": cli_hash,
        "engine": env["DAGGER_ENGINE"], "do_not_track": env.get("DO_NOT_TRACK"),
        "native_wcprof": args.profile,
        "local_otel": {key: value for key, value in env.items()
                       if key.startswith("OTEL_EXPORTER_OTLP") and key.endswith("ENDPOINT")},
        "samples_per_scenario": args.samples, "warmup_pairs_per_scenario": 1,
        "cold_claim": False, "cache_resets": False, "nonce": nonce,
        "workdirs": {side: str(path) for side, path in workdirs.items()},
        "parents": {side: values[0] for side, values in validated.items()},
        "initial_source_sha256": before[2],
        "diagnostic_limit": "cached check-log is not independent exec proof; audit actual execution in OTel",
        "status": "running",
    }
    (root / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    current = {side: values[1].copy() for side, values in validated.items()}
    for side, sources in current.items():
        for scenario, content in sources.items():
            backup = root / "originals" / side / PATHS[scenario]
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(content)
    rows = []

    def process(side, scenario, sample, diagnostic=False):
        label = f"{scenario}-{sample}-{side}" + ("-cargo-diagnostic" if diagnostic else "")
        argv = [str(binaries[side])] + (["api", "call", "rust", "check-log"] if diagnostic
                               else (["--profile"] if args.profile else []) + ["check", "rust:check"])
        log_path = root / (label + ".log")
        record = dict(label=label, scenario=scenario, sample=sample, side=side, argv=argv,
                      cwd=str(workdirs[side]), timed=not diagnostic, warmup=sample == 0,
                      exit_code=None)
        with log_path.open("xb") as log:
            record["start_unix_ns"], start = time.time_ns(), time.perf_counter_ns()
            try:
                result = subprocess.run(argv, cwd=workdirs[side], env=env,
                                        stdout=log, stderr=subprocess.STDOUT)
                record["exit_code"] = result.returncode
            finally:
                record["milliseconds"] = (time.perf_counter_ns() - start) / 1e6
                record["end_unix_ns"] = time.time_ns()
                log.flush()
                record["log_sha256"] = digest(log_path)
                with (root / "processes.jsonl").open("a") as records:
                    records.write(json.dumps(record) + "\n")
                if not diagnostic:
                    rows.append(record)
                    with (root / "timings.csv").open("a") as times:
                        csv.writer(times).writerow([scenario, sample, side, record["milliseconds"],
                                                    sample == 0, record["exit_code"]])
        require(record["exit_code"] == 0, f"{label} exited {record['exit_code']}; see {log_path}")
        return log_path

    try:
        with (root / "timings.csv").open("x") as times:
            csv.writer(times).writerow(["scenario", "sample", "side", "milliseconds", "warmup", "exit_code"])
        for scenario_index, (scenario, relative) in enumerate(PATHS.items()):
            for sample in range(args.samples + 1):
                token = f"module-edit-{nonce}-{scenario}-{sample}"
                content = edited(before[1][scenario], scenario, token)
                for side, workdir in workdirs.items():
                    for name, previous in current[side].items():
                        require((workdir / PATHS[name]).read_bytes() == previous,
                                f"fixture changed concurrently: {workdir / PATHS[name]}")
                for side, workdir in workdirs.items():
                    (workdir / relative).write_bytes(content)
                    current[side][scenario] = content
                with (root / "edits.jsonl").open("a") as edits:
                    edits.write(json.dumps(dict(scenario=scenario, sample=sample, token=token,
                                                path=relative, sha256=hashlib.sha256(content).hexdigest())) + "\n")
                pair_index = scenario_index * (args.samples + 1) + sample
                order = ("before", "after") if pair_index % 2 == 0 else ("after", "before")
                for side in order:
                    process(side, scenario, sample)
                rebuilt = {}
                for side in order:
                    log = process(side, scenario, sample, diagnostic=True).read_text(errors="replace")
                    log = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", log)
                    rebuilt[side] = sorted(set(re.findall(
                        r"^\s*(Checking|Compiling) (\S+) v([^\s]+)", log, re.MULTILINE)))
                audit = dict(scenario=scenario, sample=sample, rebuilt=rebuilt,
                             equal=rebuilt["before"] == rebuilt["after"],
                             expected_packages=sorted(EXPECTED[scenario]))
                with (root / "rebuilds.jsonl").open("a") as checks:
                    checks.write(json.dumps(audit) + "\n")
                require(audit["equal"], f"Cargo diagnostic rebuild sets differ: {audit}")
                for side, packages in rebuilt.items():
                    names = {name for _, name, _ in packages}
                    require(EXPECTED[scenario] <= names if sample == 0 else EXPECTED[scenario] == names,
                            f"unexpected affected packages in {side} {scenario} sample {sample}: {packages}")
        for side, workdir in workdirs.items():
            expected = before[2].copy()
            expected.update({PATHS[name]: hashlib.sha256(content).hexdigest()
                             for name, content in current[side].items()})
            require(source_hashes(workdir) == expected, f"unexpected source changes: {workdir}")
            validate_side(workdir, cli_hash)
        require({side: digest(path) for side, path in binaries.items()} == binary_hashes, "CLI changed during comparison")
        summary = {}
        for scenario in PATHS:
            values = {side: [row["milliseconds"] for row in rows if row["scenario"] == scenario
                             and row["side"] == side and not row["warmup"]] for side in workdirs}
            summary[scenario] = {side: {"median_ms": statistics.median(times),
                                       "min_ms": min(times), "max_ms": max(times)}
                                 for side, times in values.items()}
            summary[scenario]["paired_median_saving_ms"] = statistics.median(
                left - right for left, right in zip(values["before"], values["after"]))
        (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2), flush=True)
        metadata["status"] = "complete"
    except BaseException as error:
        metadata.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        metadata["finished_unix_ns"] = time.time_ns()
        (root / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"Results and originals retained at {root}; benchmark copies remain edited.", flush=True)


if __name__ == "__main__":
    main()
