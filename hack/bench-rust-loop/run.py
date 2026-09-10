#!/usr/bin/env python3
"""Paired ordinary-CLI check timings; separate wcprof diagnostic samples.

Uses an isolated two-crate fixture or pinned ripgrep. Not a cold-install claim.
Native Cargo uses docker exec; that lifecycle is explicitly included.
"""
import argparse
import csv
import difflib
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
import tomllib
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dagger", required=True, type=Path)
    parser.add_argument("--image", required=True, help="Same digest-pinned Rust image on both sides")
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--debug-url", default="http://localhost:6060")
    parser.add_argument("--ripgrep", type=Path, help="Clean checkout of the pinned ripgrep revision")
    parser.add_argument("--fresh-engine", help="Locally installed engine image; use a disposable empty state volume")
    parser.add_argument("--profile-first", action="store_true", help="Diagnostic first check with native wcprof enabled; not an unprofiled timing")
    parser.add_argument("--dependency-upgrade", action="store_true", help="With --ripgrep, prime bstr 1.12.0 then upgrade the application to 1.13.0 once")
    parser.add_argument("--profile-dependency-upgrade", action="store_true", help="Capture the first dependency upgrade with wcprof; label its timing as profiled")
    parser.add_argument("--dependency-first", choices=("native", "dagger"), default="native", help="First side for the single dependency upgrade; alternate across isolated runs")
    parser.add_argument("--trace-phases", action="store_true", help="Diagnostic shell timing of source reconciliation and Cargo; changes the Dagger action")
    args = parser.parse_args()
    if "@sha256:" not in args.image or args.samples < 1:
        parser.error("use a digest-pinned image and at least one sample")
    if args.dependency_upgrade and not args.ripgrep:
        parser.error("--dependency-upgrade requires --ripgrep")
    if args.profile_dependency_upgrade and not args.dependency_upgrade:
        parser.error("--profile-dependency-upgrade requires --dependency-upgrade")
    args.dagger = args.dagger.resolve()
    root = Path(tempfile.mkdtemp(prefix="dagger-rust-loop-"))
    print(root, flush=True)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("_EXPERIMENTAL_DAGGER_") or key in {"DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN"}:
            env.pop(key)
    container = "rust-loop-" + root.name
    fresh_engine = container + "-engine"
    volume_created = False
    engine_created = False
    first_use = {}
    if args.fresh_engine:
        for category in ("CONFIG", "CACHE", "DATA", "STATE"):
            env[f"XDG_{category}_HOME"] = str(root / "cli-state" / category.lower())
        env.pop("DAGGER_CONFIG", None)
        env["DAGGER_ENGINE"] = "container://" + fresh_engine
    module = Path(__file__).resolve().parent / "module"
    rows = []
    revision = "3fce3b5bb0236da2df6d99672afb8a719642eca7"
    if args.ripgrep:
        args.ripgrep = args.ripgrep.resolve()
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.ripgrep, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=args.ripgrep, text=True)
        if actual != revision or dirty:
            parser.error("ripgrep must be a clean checkout of " + revision)

    def run(command, label, cwd=None, expected=0):
        with (root / (label + ".log")).open("wb") as log:
            wall_start = time.time_ns()
            start = time.perf_counter_ns()
            result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            wall_end = time.time_ns()
        # Process boundaries expose startup/shutdown outside the root OTel span.
        # Write this diagnostic record after the measured process has exited.
        with (root / "processes.jsonl").open("a") as output:
            output.write(json.dumps({"label": label, "start_unix_ns": wall_start,
                                     "end_unix_ns": wall_end, "milliseconds": elapsed,
                                     "exit_code": result.returncode}) + "\n")
        if result.returncode != expected:
            raise RuntimeError(f"{label}: exit {result.returncode}; see {root / (label + '.log')}")
        return elapsed

    def write(side, relative, content):
        path = root / side / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    for side in ("native", "dagger"):
        if args.ripgrep:
            shutil.copytree(args.ripgrep, root / side, ignore=shutil.ignore_patterns(".git", "target"))
        else:
            write(side, "Cargo.toml", '[workspace]\nmembers = ["app", "library"]\nresolver = "2"\n')
            write(side, "Cargo.lock", 'version = 4\n[[package]]\nname = "app"\nversion = "0.1.0"\ndependencies = ["library"]\n[[package]]\nname = "library"\nversion = "0.1.0"\n')
            write(side, "app/Cargo.toml", '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n[dependencies]\nlibrary = { path = "../library" }\n')
            write(side, "library/Cargo.toml", '[package]\nname = "library"\nversion = "0.1.0"\nedition = "2021"\n')
            write(side, "app/src/main.rs", 'fn main() { println!("{}", library::value()); }\n')
            write(side, "library/src/lib.rs", 'pub fn value() -> u64 { 0 }\n')
        run(["git", "init", "-q"], "init-" + side, root / side)
    if args.dependency_upgrade:
        upgrade = {name: (root / "native" / name).read_text() for name in ("Cargo.toml", "Cargo.lock")}
        assert upgrade["Cargo.toml"].count('bstr = "1.7.0"') == 1
        upgrade["Cargo.toml"] = upgrade["Cargo.toml"].replace('bstr = "1.7.0"', 'bstr = "=1.13.0"')
        for side in ("native", "dagger"):
            run(["git", "apply", str(module.parent / "fixtures" / "ripgrep-bstr-1.12.0.patch")],
                "dependency-baseline-" + side, root / side)
        baseline = {name: (root / "native" / name).read_text() for name in upgrade}
        # The committed baseline was resolved by Cargo. Guard against accidentally
        # turning this into an upgrade of unrelated packages in a future edit.
        before_packages = tomllib.loads(baseline["Cargo.lock"])["package"]
        after_packages = tomllib.loads(upgrade["Cargo.lock"])["package"]
        assert [p for p in before_packages if p["name"] != "bstr"] == [p for p in after_packages if p["name"] != "bstr"]
        assert [p["version"] for p in before_packages if p["name"] == "bstr"] == ["1.12.0"]
        assert [p["version"] for p in after_packages if p["name"] == "bstr"] == ["1.13.0"]
        diff = "".join("".join(difflib.unified_diff(baseline[name].splitlines(True), upgrade[name].splitlines(True),
                                                   fromfile="before/" + name, tofile="after/" + name)) for name in upgrade)
        (root / "dependency-upgrade.diff").write_text(diff)
    app_path = "crates/core/flags/doc/version.rs" if args.ripgrep else "app/src/main.rs"
    library_path = "crates/printer/src/standard.rs" if args.ripgrep else "library/src/lib.rs"
    app_base = (root / "native" / app_path).read_text()
    library_base = (root / "native" / library_path).read_text()

    def app_edit(sample):
        if args.ripgrep:
            assert 'format!("ripgrep {digits}")' in app_base
            return app_base.replace('format!("ripgrep {digits}")', f'format!("ripgrep {{digits}} bench-{sample}")')
        return f'fn main() {{ println!("sample-{sample}: {{}}", library::value()); }}\n'

    def library_edit(sample):
        if args.ripgrep:
            assert "[Omitted long context line]" in library_base
            return library_base.replace("[Omitted long context line]", f"[Omitted long context line bench-{sample}]")
        return f'pub fn value() -> u64 {{ {sample} }}\n'
    write("dagger", "dagger.toml", f'[modules.rust]\nsource = {json.dumps(str(module))}\n[modules.rust.settings]\nimage = {json.dumps(args.image)}\ncacheKey = {json.dumps(container)}\n')
    if args.trace_phases:
        with (root / "dagger" / "dagger.toml").open("a") as config:
            config.write("tracePhases = true\n")
    metadata = {"image": args.image, "dagger": str(args.dagger), "samples": args.samples,
                "native_lifecycle": "docker exec", "fixture": "synthetic two-crate workspace",
                "engine": env.get("DAGGER_ENGINE"), "cold_claim": False}
    metadata["cli_sha256"] = hashlib.file_digest(args.dagger.open("rb"), "sha256").hexdigest()
    metadata["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=module, text=True).strip()
    metadata["source_diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=module)).hexdigest()
    metadata["module_sha256"] = hashlib.sha256((module / "main.dang").read_bytes()).hexdigest()
    metadata["do_not_track"] = env.get("DO_NOT_TRACK")
    metadata["reset_mode"] = "empty-engine-and-cli-state" if args.fresh_engine else "existing-engine"
    metadata["preinstalled"] = ["Docker", "Dagger CLI", "engine image", "local module source", "native Rust image"]
    metadata["first_check_profiled"] = args.profile_first
    metadata["shell_phase_instrumentation"] = args.trace_phases
    metadata["dependency_upgrade"] = {"package": "bstr", "from": "1.12.0", "to": "1.13.0",
                                      "transitions_per_run": 1, "first": args.dependency_first,
                                      "profiled": args.profile_dependency_upgrade} if args.dependency_upgrade else None
    if args.ripgrep:
        metadata.update(fixture="ripgrep", fixture_revision=revision)
    (root / "metadata.json").write_text(json.dumps(metadata, indent=2))

    def commands(profile=False):
        return {
            "native": ["docker", "exec", container, "cargo", "check", "--workspace", "--locked"],
            "dagger": [str(args.dagger)] + (["--profile"] if profile else []) + ["check", "rust:check"],
        }

    def dump(name):
        try:
            with urllib.request.urlopen(args.debug_url + "/debug/wcprof/dump", timeout=30) as response:
                (root / name).write_bytes(response.read())
        except urllib.error.HTTPError as error:
            if name == "before.wcprof" and error.code == 503:
                # A fresh engine has no recorder until profiling first starts.
                # This pre-capture drain is optional; actual captures must work.
                return
            raise

    def save_timings():
        with (root / "timings.csv").open("w") as output:
            writer = csv.writer(output)
            writer.writerow(["scenario", "sample", "side", "milliseconds", "profiled"])
            writer.writerows(rows)

    try:
        run(["docker", "run", "-d", "--name", container, "-v", f"{root / 'native'}:/src",
             "-w", "/src", "-e", "CARGO_TARGET_DIR=/target", args.image, "sleep", "infinity"], "native-start")
        if args.fresh_engine:
            # Resolve locally before starting: pulling/installing the engine is
            # explicitly not covered by this partial first-use measurement.
            metadata["engine_image_id"] = subprocess.check_output(
                ["docker", "image", "inspect", args.fresh_engine, "--format", "{{.Id}}"], text=True).strip()
            (root / "metadata.json").write_text(json.dumps(metadata, indent=2))
            provision_start = time.perf_counter_ns()
            run(["docker", "volume", "create", "--label", f"dagger.rust-bench={root.name}", fresh_engine], "volume-create")
            volume_created = True
            run(["docker", "run", "-d", "--privileged", "--name", fresh_engine,
                 "--label", f"dagger.rust-bench={root.name}",
                 "-v", f"{fresh_engine}:/var/lib/dagger",
                 "-p", "127.0.0.1::6060", metadata["engine_image_id"],
                 "--debugaddr=0.0.0.0:6060"], "engine-start")
            engine_created = True
            first_use["engine_provision_ms"] = (time.perf_counter_ns() - provision_start) / 1e6
            binding = subprocess.check_output(["docker", "port", fresh_engine, "6060/tcp"], text=True).strip()
            args.debug_url = "http://" + binding
        initial_order = ("dagger", "native") if args.fresh_engine else ("native", "dagger")
        for side in initial_order:
            command = commands(profile=args.profile_first and side == "dagger")[side]
            first_use[side + "_first_check_ms"] = run(command, "warmup-" + side, root / side)
            if args.fresh_engine and side == "dagger":
                first_use["dagger_provision_plus_first_check_ms"] = (time.perf_counter_ns() - provision_start) / 1e6
            (root / "first-use.json").write_text(json.dumps(first_use, indent=2))
            if args.profile_first and side == "dagger":
                dump("first-check.wcprof")
        if args.fresh_engine:
            first_use["native_existing_cache_check_ms"] = run(commands()["native"], "native-existing-cache", root / "native")
            (root / "first-use.json").write_text(json.dumps(first_use, indent=2))
            print("first-use", first_use, flush=True)
        for scenario in ("exact", "application", "workspace-library"):
            for sample in range(args.samples):
                for side in ("native", "dagger"):
                    if scenario == "application":
                        write(side, app_path, app_edit(sample))
                    elif scenario == "workspace-library":
                        write(side, library_path, library_edit(sample + 1))
                order = ("native", "dagger") if sample % 2 == 0 else ("dagger", "native")
                for side in order:
                    elapsed = run(commands()[side], f"{scenario}-{sample}-{side}", root / side)
                    rows.append([scenario, sample, side, elapsed, args.trace_phases and side == "dagger"])
                if args.ripgrep:
                    # Retrieval is outside the timed commands. The identical
                    # action should already be evaluated; preserve Cargo's
                    # Checking/Compiling lines for invalidation auditing.
                    run([str(args.dagger), "api", "call", "rust", "check-log"],
                        f"{scenario}-{sample}-cargo-diagnostic", root / "dagger")
                save_timings()
        if args.dependency_upgrade:
            # Exactly one new dependency version per isolated run. Repeated
            # A->B->A transitions would mix artifact reuse with recompilation.
            for side in ("native", "dagger"):
                for name, content in upgrade.items():
                    assert (root / side / name).read_text() == baseline[name]
                    write(side, name, content)
            if args.profile_dependency_upgrade:
                dump("before.wcprof")
            dependency_order = (args.dependency_first, "dagger" if args.dependency_first == "native" else "native")
            for side in dependency_order:
                profiled = args.profile_dependency_upgrade and side == "dagger"
                elapsed = run(commands(profile=profiled)[side], "dependency-upgrade-" + side, root / side)
                rows.append(["dependency-upgrade", 0, side, elapsed, profiled or (args.trace_phases and side == "dagger")])
                if profiled:
                    dump("dependency-upgrade.wcprof")
            run([str(args.dagger), "api", "call", "rust", "check-log"], "dependency-upgrade-cargo-diagnostic", root / "dagger")
            rebuilt = {}
            for side, log_name in (("native", "dependency-upgrade-native.log"), ("dagger", "dependency-upgrade-cargo-diagnostic.log")):
                log_text = (root / log_name).read_text()
                rebuilt[side] = sorted(set(re.findall(r"^\s*(?:Checking|Compiling) (\S+) v([^\s]+)", log_text, re.MULTILINE)))
                assert ("bstr", "1.13.0") in rebuilt[side], (side, rebuilt[side])
                assert all(name != "memchr" for name, _ in rebuilt[side]), (side, "unrelated memchr rebuilt")
                for name, content in upgrade.items():
                    assert (root / side / name).read_text() == content, (side, name, "Cargo changed locked inputs")
            (root / "dependency-rebuilds.json").write_text(json.dumps(rebuilt, indent=2))
            assert rebuilt["native"] == rebuilt["dagger"], rebuilt
            save_timings()
            for side in ("dagger", "native"):
                elapsed = run(commands()[side], "dependency-followup-" + side, root / side)
                rows.append(["dependency-followup", 0, side, elapsed, args.trace_phases and side == "dagger"])
            save_timings()
        # Failure then repair validates fresh source is actually consumed.
        invalid_source = library_base + '\ncompile_error!("invalidation-probe");\n'
        write("dagger", library_path, invalid_source)
        run(commands()["dagger"], "failure-probe", root / "dagger", expected=101)
        write("dagger", library_path, library_edit(123456789))
        dump("before.wcprof")
        run(commands(profile=True)["dagger"], "profile-library-repair", root / "dagger")
        dump("library-repair.wcprof")
        # Revisit an older immutable source snapshot after a newer successful
        # compile populated the mutable target. Timestamp-only freshness can
        # incorrectly accept this previously rejected source.
        write("dagger", library_path, invalid_source)
        run(commands()["dagger"], "failure-revisit", root / "dagger", expected=101)
        write("dagger", library_path, library_edit(123456789))
        run(commands()["dagger"], "repair-revisit", root / "dagger")
        dump("revisit.wcprof")
        run(commands(profile=True)["dagger"], "profile-exact", root / "dagger")
        dump("exact.wcprof")
        write("dagger", app_path, app_edit("profile"))
        run(commands(profile=True)["dagger"], "profile-application", root / "dagger")
        dump("application.wcprof")
        for scenario in dict.fromkeys(r[0] for r in rows):
            print(scenario, {side: statistics.median(r[3] for r in rows if r[0] == scenario and r[2] == side)
                             for side in ("native", "dagger")}, flush=True)
    finally:
        subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL, check=False)
        if engine_created:
            with (root / "engine.log").open("wb") as log:
                subprocess.run(["docker", "logs", fresh_engine], stdout=log, stderr=subprocess.STDOUT, check=False)
            subprocess.run(["docker", "rm", "-f", fresh_engine], stdout=subprocess.DEVNULL, check=False)
        if volume_created:
            subprocess.run(["docker", "volume", "rm", fresh_engine], stdout=subprocess.DEVNULL, check=True)
            print("Removed disposable engine/cache; benchmark files retained at", root, flush=True)


if __name__ == "__main__":
    main()
