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
        write(side, "Cargo.toml", '[workspace]\nmembers = ["app", "library"]\nresolver = "2"\n')
        write(side, "Cargo.lock", 'version = 4\n[[package]]\nname = "app"\nversion = "0.1.0"\ndependencies = ["library"]\n[[package]]\nname = "library"\nversion = "0.1.0"\n')
        write(side, "app/Cargo.toml", '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n[dependencies]\nlibrary = { path = "../library" }\n')
        write(side, "library/Cargo.toml", '[package]\nname = "library"\nversion = "0.1.0"\nedition = "2021"\n')
        write(side, "app/src/main.rs", 'fn main() { println!("{}", library::value()); }\n')
        write(side, "library/src/lib.rs", 'pub fn value() -> u64 { 0 }\n')
        run(["git", "init", "-q"], "init-" + side, root / side)
    write("dagger", "dagger.toml", f'[modules.rust]\nsource = {json.dumps(str(module))}\n[modules.rust.settings]\nimage = {json.dumps(args.image)}\ncacheKey = {json.dumps(container)}\n')
    metadata = {"image": args.image, "dagger": str(args.dagger), "samples": args.samples,
                "native_lifecycle": "docker exec", "fixture": "synthetic two-crate workspace",
                "engine": env.get("DAGGER_ENGINE"), "cold_claim": False}
    metadata["cli_sha256"] = hashlib.file_digest(args.dagger.open("rb"), "sha256").hexdigest()
    metadata["source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=module, text=True).strip()
    metadata["source_diff_sha256"] = hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=module)).hexdigest()
    metadata["module_sha256"] = hashlib.sha256((module / "main.dang").read_bytes()).hexdigest()
    metadata["do_not_track"] = env.get("DO_NOT_TRACK")
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
                        write(side, "app/src/main.rs", f'fn main() {{ println!("sample-{sample}: {{}}", library::value()); }}\n')
                    elif scenario == "workspace-library":
                        write(side, "library/src/lib.rs", f'pub fn value() -> u64 {{ {sample + 1} }}\n')
                order = ("native", "dagger") if sample % 2 == 0 else ("dagger", "native")
                for side in order:
                    elapsed = run(commands()[side], f"{scenario}-{sample}-{side}", root / side)
                    rows.append([scenario, sample, side, elapsed])
                with (root / "timings.csv").open("w") as output:
                    writer = csv.writer(output)
                    writer.writerow(["scenario", "sample", "side", "milliseconds"])
                    writer.writerows(rows)
        # Failure then repair validates fresh source is actually consumed.
        write("dagger", "library/src/lib.rs", 'compile_error!("invalidation-probe");\n')
        run(commands()["dagger"], "failure-probe", root / "dagger", expected=101)
        write("dagger", "library/src/lib.rs", 'pub fn value() -> u64 { 123456789 }\n')
        dump("before.wcprof")
        run(commands(profile=True)["dagger"], "profile-library-repair", root / "dagger")
        dump("library-repair.wcprof")
        run(commands(profile=True)["dagger"], "profile-exact", root / "dagger")
        dump("exact.wcprof")
        write("dagger", "app/src/main.rs", 'fn main() { println!("profile-edit: {}", library::value()); }\n')
        run(commands(profile=True)["dagger"], "profile-application", root / "dagger")
        dump("application.wcprof")
        for scenario in ("exact", "application", "workspace-library"):
            print(scenario, {side: statistics.median(r[3] for r in rows if r[0] == scenario and r[2] == side)
                             for side in ("native", "dagger")}, flush=True)
    finally:
        subprocess.run(["docker", "rm", "-f", container], stdout=subprocess.DEVNULL, check=False)


if __name__ == "__main__":
    main()
