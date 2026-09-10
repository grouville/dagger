#!/usr/bin/env python3
"""Paired ordinary-CLI check timings; separate wcprof diagnostic samples.

Uses an isolated two-crate fixture. Not a real-project or cold-install claim.
Native Cargo uses docker exec; that lifecycle is explicitly included.
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dagger", required=True, type=Path)
    parser.add_argument("--image", required=True, help="Same digest-pinned Rust image on both sides")
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--debug-url", default="http://localhost:6060")
    parser.add_argument("--ripgrep", type=Path, help="Clean checkout of the pinned ripgrep revision")
    args = parser.parse_args()
    if "@sha256:" not in args.image or args.samples < 1:
        parser.error("use a digest-pinned image and at least one sample")
    args.dagger = args.dagger.resolve()
    root = Path(tempfile.mkdtemp(prefix="dagger-rust-loop-"))
    print(root, flush=True)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("_EXPERIMENTAL_DAGGER_") or key in {"DAGGER_SESSION_PORT", "DAGGER_SESSION_TOKEN"}:
            env.pop(key)
    container = "rust-loop-" + root.name
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
            start = time.perf_counter_ns()
            result = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
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
    metadata = {"image": args.image, "dagger": str(args.dagger), "samples": args.samples,
                "native_lifecycle": "docker exec", "fixture": "synthetic two-crate workspace",
                "engine": env.get("DAGGER_ENGINE"), "cold_claim": False}
    metadata["cli_sha256"] = hashlib.file_digest(args.dagger.open("rb"), "sha256").hexdigest()
    metadata["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=module, text=True).strip()
    metadata["source_diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=module)).hexdigest()
    metadata["module_sha256"] = hashlib.sha256((module / "main.dang").read_bytes()).hexdigest()
    metadata["do_not_track"] = env.get("DO_NOT_TRACK")
    if args.ripgrep:
        metadata.update(fixture="ripgrep", fixture_revision=revision)
    (root / "metadata.json").write_text(json.dumps(metadata, indent=2))

    def commands(profile=False):
        return {
            "native": ["docker", "exec", container, "cargo", "check", "--workspace", "--locked"],
            "dagger": [str(args.dagger)] + (["--profile"] if profile else []) + ["check", "rust:check"],
        }

    def dump(name):
        with urllib.request.urlopen(args.debug_url + "/debug/wcprof/dump", timeout=30) as response:
            (root / name).write_bytes(response.read())

    try:
        run(["docker", "run", "-d", "--name", container, "-v", f"{root / 'native'}:/src",
             "-w", "/src", "-e", "CARGO_TARGET_DIR=/target", args.image, "sleep", "infinity"], "native-start")
        for side, command in commands().items():
            run(command, "warmup-" + side, root / side)
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
                    rows.append([scenario, sample, side, elapsed])
                if args.ripgrep:
                    # Retrieval is outside the timed commands. The identical
                    # action should already be evaluated; preserve Cargo's
                    # Checking/Compiling lines for invalidation auditing.
                    run([str(args.dagger), "api", "call", "rust", "check-log"],
                        f"{scenario}-{sample}-cargo-diagnostic", root / "dagger")
                with (root / "timings.csv").open("w") as output:
                    writer = csv.writer(output)
                    writer.writerow(["scenario", "sample", "side", "milliseconds"])
                    writer.writerows(rows)
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
        for scenario in ("exact", "application", "workspace-library"):
            print(scenario, {side: statistics.median(r[3] for r in rows if r[0] == scenario and r[2] == side)
                             for side in ("native", "dagger")}, flush=True)
    finally:
        subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    main()
