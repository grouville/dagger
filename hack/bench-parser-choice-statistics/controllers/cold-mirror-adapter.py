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
    # Keep all maintained workload/fixture paths at the frozen baseline. Only
    # cold resource guards and post-timer diagnostics differ in this adapter.
    benchmark_dir = Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop')
    repository = benchmark_dir.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dagger", required=True, type=Path)
    parser.add_argument("--module-dir", type=Path, default=benchmark_dir / "module",
                        help="Opt-in module variant; defaults to the committed benchmark module")
    parser.add_argument("--image", required=True, help="Same digest-pinned Rust image on both sides")
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--debug-url", default="http://localhost:6060")
    parser.add_argument("--ripgrep", type=Path, help="Clean checkout of the pinned ripgrep revision")
    parser.add_argument("--fresh-engine", help="Locally installed engine image; use a disposable empty state volume")
    parser.add_argument("--engine-config", type=Path, help="Diagnostic mirror-only JSON config mounted read-only into the owned fresh engine")
    parser.add_argument("--profile-first", action="store_true", help="Diagnostic first check with native wcprof enabled; not an unprofiled timing")
    parser.add_argument("--dependency-upgrade", action="store_true", help="With --ripgrep, prime bstr 1.12.0 then upgrade the application to 1.13.0 once")
    parser.add_argument("--profile-dependency-upgrade", action="store_true", help="Capture the first dependency upgrade with wcprof; label its timing as profiled")
    parser.add_argument("--dependency-first", choices=("native", "dagger"), default="native", help="First side for the single dependency upgrade; alternate across isolated runs")
    parser.add_argument("--trace-phases", action="store_true", help="Diagnostic shell timing of source reconciliation and Cargo; changes the Dagger action")
    parser.add_argument("--pinned-source-sync", action="store_true", help="Experimental checksum-pinned Debian rsync packages instead of runtime APT resolution; only the pinned bookworm/amd64 fixture")
    parser.add_argument("--project-toolchain", type=Path, help="Copy this rust-toolchain.toml into both isolated workspaces before the first check; installation is inside the timer")
    parser.add_argument("--prepare-project-toolchain", action="store_true", help="Experimental immutable toolchain setup keyed by root toolchain files before edit-sensitive source")
    args = parser.parse_args()
    if "@sha256:" not in args.image or args.samples < 1:
        parser.error("use a digest-pinned image and at least one sample")
    if args.dependency_upgrade and not args.ripgrep:
        parser.error("--dependency-upgrade requires --ripgrep")
    if args.profile_dependency_upgrade and not args.dependency_upgrade:
        parser.error("--profile-dependency-upgrade requires --dependency-upgrade")
    if args.pinned_source_sync and args.image != "rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b":
        parser.error("--pinned-source-sync is validated only against the pinned slim-bookworm/amd64 image")
    module = args.module_dir.resolve()
    for name in ("main.dang", "dagger-module.toml"):
        if not (module / name).is_file():
            parser.error(f"--module-dir requires a file at {module / name}")
    engine_config = args.engine_config.resolve(strict=True) if args.engine_config else None
    if engine_config is not None:
        assert args.fresh_engine, "mirror override requires an owned fresh engine"
        assert json.loads(engine_config.read_text()) == {"registries": {"docker.io": {"mirrors": []}}}
    toolchain_contents = args.project_toolchain.read_bytes() if args.project_toolchain else None
    if toolchain_contents is not None:
        tomllib.loads(toolchain_contents.decode())
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
    native_created = False
    first_use = {}
    if args.fresh_engine:
        for category in ("CONFIG", "CACHE", "DATA", "STATE"):
            env[f"XDG_{category}_HOME"] = str(root / "cli-state" / category.lower())
        env.pop("DAGGER_CONFIG", None)
        env["DAGGER_ENGINE"] = "container://" + fresh_engine
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
        if toolchain_contents is not None:
            if any((root / side / name).exists() for name in ("rust-toolchain", "rust-toolchain.toml")):
                parser.error("--project-toolchain must not replace an existing project toolchain file")
            (root / side / "rust-toolchain.toml").write_bytes(toolchain_contents)
        run(["git", "init", "-q"], "init-" + side, root / side)
    if args.dependency_upgrade:
        upgrade = {name: (root / "native" / name).read_text() for name in ("Cargo.toml", "Cargo.lock")}
        assert upgrade["Cargo.toml"].count('bstr = "1.7.0"') == 1
        upgrade["Cargo.toml"] = upgrade["Cargo.toml"].replace('bstr = "1.7.0"', 'bstr = "=1.13.0"')
        for side in ("native", "dagger"):
            run(["git", "apply", str(benchmark_dir / "fixtures" / "ripgrep-bstr-1.12.0.patch")],
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
    if args.pinned_source_sync:
        with (root / "dagger" / "dagger.toml").open("a") as config:
            config.write("pinnedSourceSync = true\n")
    if args.prepare_project_toolchain:
        with (root / "dagger" / "dagger.toml").open("a") as config:
            config.write("prepareProjectToolchain = true\n")
    metadata = {"image": args.image, "dagger": str(args.dagger), "samples": args.samples,
                "native_lifecycle": "docker exec", "fixture": "synthetic two-crate workspace",
                "engine": env.get("DAGGER_ENGINE"), "cold_claim": False}
    metadata["cli_sha256"] = hashlib.file_digest(args.dagger.open("rb"), "sha256").hexdigest()
    metadata["source_root"] = str(repository)
    metadata["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    metadata["source_diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=repository)).hexdigest()
    metadata["module_dir"] = str(module)
    metadata["module_sha256"] = hashlib.sha256((module / "main.dang").read_bytes()).hexdigest()
    metadata["module_config_sha256"] = hashlib.sha256((module / "dagger-module.toml").read_bytes()).hexdigest()
    metadata["do_not_track"] = env.get("DO_NOT_TRACK")
    metadata["diagnostic_engine_config"] = str(engine_config) if engine_config else None
    metadata["diagnostic_engine_config_sha256"] = hashlib.sha256(engine_config.read_bytes()).hexdigest() if engine_config else None
    metadata["reset_mode"] = "empty-engine-and-cli-state" if args.fresh_engine else "existing-engine"
    metadata["preinstalled"] = ["Docker", "Dagger CLI", "engine image", "local module source", "native Rust image"]
    metadata["first_check_profiled"] = args.profile_first
    metadata["shell_phase_instrumentation"] = args.trace_phases
    metadata["source_sync_delivery"] = "pinned-debian-packages" if args.pinned_source_sync else "runtime-apt"
    metadata["prepare_project_toolchain"] = args.prepare_project_toolchain
    metadata["project_toolchain_sha256"] = hashlib.sha256(toolchain_contents).hexdigest() if toolchain_contents is not None else None
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
        if name in ('first-check.wcprof', 'application.wcprof', 'restart-exact.wcprof'):
            # Diagnostic only: the matching command has already exited and
            # its process timer is closed. Do not prefetch/prime any result.
            with urllib.request.urlopen(args.debug_url + '/debug/dagql/cache', timeout=30) as response:
                (root / (name + '.cache.json')).write_bytes(response.read())

    def save_timings():
        with (root / "timings.csv").open("w") as output:
            writer = csv.writer(output)
            writer.writerow(["scenario", "sample", "side", "milliseconds", "profiled"])
            writer.writerows(rows)

    try:
        for owned_name in (container, fresh_engine):
            assert not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + owned_name + '$'], text=True).strip(), owned_name
        assert subprocess.run(['docker', 'volume', 'inspect', fresh_engine], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0
        run(["docker", "run", "--pull=never", "-d", "--name", container,
             "--label", f"dagger.rust-bench={root.name}", "-v", f"{root / 'native'}:/src",
             "-w", "/src", "-e", "CARGO_TARGET_DIR=/target", args.image, "sleep", "infinity"], "native-start")
        native_created = True
        if args.fresh_engine:
            # Resolve locally before starting: pulling/installing the engine is
            # explicitly not covered by this partial first-use measurement.
            metadata["engine_image_id"] = subprocess.check_output(
                ["docker", "image", "inspect", args.fresh_engine, "--format", "{{.Id}}"], text=True).strip()
            (root / "metadata.json").write_text(json.dumps(metadata, indent=2))
            provision_start = time.perf_counter_ns()
            run(["docker", "volume", "create", "--label", f"dagger.rust-bench={root.name}", fresh_engine], "volume-create")
            volume_created = True
            run(["docker", "run", "--pull=never", "-d", "--privileged", "--name", fresh_engine,
                 "--label", f"dagger.rust-bench={root.name}",
                 "-v", f"{fresh_engine}:/var/lib/dagger",
                 "-p", "127.0.0.1::6060"] +
                (["--mount", f"type=bind,src={engine_config},dst=/etc/dagger/engine.json,readonly"] if engine_config else []) +
                [metadata["engine_image_id"],
                 "--debugaddr=0.0.0.0:6060"], "engine-start")
            engine_created = True
            first_use["engine_provision_ms"] = (time.perf_counter_ns() - provision_start) / 1e6
            binding = subprocess.check_output(["docker", "port", fresh_engine, "6060/tcp"], text=True).strip()
            args.debug_url = "http://" + binding
            metadata['engine_inspect'] = json.loads(subprocess.check_output(['docker', 'inspect', fresh_engine], text=True))[0]
            metadata['diagnostic_debug_url'] = args.debug_url
            metadata['adapter_sha256'] = hashlib.file_digest(Path(__file__).open('rb'), 'sha256').hexdigest()
            (root / 'metadata.json').write_text(json.dumps(metadata, indent=2))
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
        if args.fresh_engine:
            # Separate persistence/lease validation, never part of cold or
            # steady-state timing. Restart only this verified owned engine.
            before_restart = json.loads(subprocess.check_output(['docker', 'inspect', fresh_engine], text=True))[0]
            assert before_restart['Id'] == metadata['engine_inspect']['Id']
            assert before_restart['Image'] == metadata['engine_image_id']
            assert before_restart['Config']['Labels']['dagger.rust-bench'] == root.name
            assert any(mount.get('Name') == fresh_engine and mount['Destination'] == '/var/lib/dagger' for mount in before_restart['Mounts'])
            run(['docker', 'restart', fresh_engine], 'engine-restart')
            after_restart = json.loads(subprocess.check_output(['docker', 'inspect', fresh_engine], text=True))[0]
            assert after_restart['Id'] == before_restart['Id'] and after_restart['Image'] == before_restart['Image']
            assert after_restart['State']['StartedAt'] != before_restart['State']['StartedAt']
            (root / 'restart-identity.json').write_text(json.dumps(dict(before=before_restart, after=after_restart), indent=2))
            # Docker may reassign an ephemeral published host port on restart.
            # Refresh only the diagnostic endpoint; workload uses container://.
            binding = subprocess.check_output(['docker', 'port', fresh_engine, '6060/tcp'], text=True).strip()
            args.debug_url = 'http://' + binding
            run(commands(profile=True)['dagger'], 'profile-restart-exact', root / 'dagger')
            dump('restart-exact.wcprof')
        for scenario in dict.fromkeys(r[0] for r in rows):
            print(scenario, {side: statistics.median(r[3] for r in rows if r[0] == scenario and r[2] == side)
                             for side in ("native", "dagger")}, flush=True)
    finally:
        if native_created:
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
