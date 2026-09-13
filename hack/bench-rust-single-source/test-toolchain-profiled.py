#!/usr/bin/env python3
"""Correctness-only toolchain transitions through standalone Dagger commands.

Uses the pinned linux/amd64 fixture image; not a performance or cold-use claim.
Component state is read directly from the immutable result, never via a rustup
command that could install missing components and mask an error.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    benchmark_dir = Path("/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop")
    repository = benchmark_dir.parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dagger", required=True, type=Path)
    parser.add_argument("--module-dir", type=Path, default=benchmark_dir / "module",
                        help="Opt-in module variant; defaults to the committed benchmark module")
    args = parser.parse_args()
    dagger = args.dagger.resolve()
    module = args.module_dir.resolve()
    for name in ("main.dang", "dagger-module.toml"):
        if not (module / name).is_file():
            parser.error(f"--module-dir requires a file at {module / name}")
    root = Path(tempfile.mkdtemp(prefix="dagger-rust-toolchain-test-"))
    print(root, flush=True)
    with dagger.open("rb") as cli:
        cli_sha256 = hashlib.file_digest(cli, "sha256").hexdigest()
    metadata = {
        "dagger": str(dagger),
        "cli_sha256": cli_sha256,
        "source_root": str(repository),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip(),
        "source_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=repository)).hexdigest(),
        "module_dir": str(module),
        "module_sha256": hashlib.sha256((module / "main.dang").read_bytes()).hexdigest(),
        "module_config_sha256": hashlib.sha256((module / "dagger-module.toml").read_bytes()).hexdigest(),
        "purpose": "correctness-only, checks wcprof-enabled",
    }
    (root / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    source = root / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "src").mkdir()
    (source / "Cargo.toml").write_text('[package]\nname = "toolchain-probe"\nversion = "0.1.0"\nedition = "2021"\n')
    (source / "Cargo.lock").write_text('version = 4\n[[package]]\nname = "toolchain-probe"\nversion = "0.1.0"\n')
    app = source / "src/main.rs"
    app.write_text('fn main() { println!("initial"); }\n')
    (source / "dagger.toml").write_text(
        '[modules.rust]\nsource = ' + json.dumps(str(module)) + '\n'
        '[modules.rust.settings]\n'
        'image = "rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b"\n'
        'cacheKey = ' + json.dumps(root.name) + '\n'
        'pinnedSourceSync = true\nprepareProjectToolchain = true\n'
    )

    def run(label, command, expected=0):
        with (root / (label + ".stdout")).open("xb") as output, (root / (label + ".stderr")).open("xb") as errors:
            wall_start, start = time.time_ns(), time.perf_counter_ns()
            result = subprocess.run([str(dagger), *command], cwd=source, stdout=output, stderr=errors)
            end, wall_end = time.perf_counter_ns(), time.time_ns()
        with (root / "processes.jsonl").open("a") as records:
            records.write(json.dumps(dict(label=label, command=command, start_unix_ns=wall_start,
                end_unix_ns=wall_end, milliseconds=(end - start) / 1e6, exit_code=result.returncode,
                purpose="correctness-only")) + "\n")
        assert result.returncode == expected, (label, result.returncode, expected, str(root))
        return (root / (label + ".stdout")).read_text()

    def check(label, expected=0):
        # Preserve exact inputs even though the working copy is edited below.
        inputs = {name: (source / name).read_text() if (source / name).exists() else None
                  for name in ("rust-toolchain", "rust-toolchain.toml", "src/main.rs")}
        (root / (label + ".inputs.json")).write_text(json.dumps(inputs, indent=2) + "\n")
        run(label, ["--profile", "check", "rust:check"], expected)

    def components(label, expected):
        manifest = run(label + "-components", ["api", "call", "rust", "toolchain-files", "file", "--path",
            "1.97.1-x86_64-unknown-linux-gnu/lib/rustlib/components", "contents"])
        installed = {line.removesuffix("-x86_64-unknown-linux-gnu") for line in manifest.splitlines()}
        actual = installed & {"rustfmt-preview", "clippy-preview"}
        assert actual == expected, (label, actual, expected, manifest)

    config = source / "rust-toolchain.toml"
    fmt = '[toolchain]\nchannel = "1.97.1"\nprofile = "minimal"\ncomponents = ["rustfmt"]\n'
    config.write_text(fmt)
    check("initial-fmt")
    components("initial-fmt", {"rustfmt-preview"})

    config.write_text(fmt.replace('["rustfmt"]', '["rustfmt", "clippy"]'))
    check("add-clippy")
    components("add-clippy", {"rustfmt-preview", "clippy-preview"})

    app.write_text('compile_error!("toolchain-cache-must-not-hide-source-edits");\nfn main() {}\n')
    check("source-failure", 101)
    app.write_text('fn main() { println!("repaired"); }\n')
    check("source-repair")

    invalid = '[toolchain]\nchannel = "dagger-invalid-toolchain-probe"\n'
    config.write_text(invalid)
    check("invalid-config", 1)
    config.write_text(fmt)
    check("revisit-fmt-config")
    components("revisit-fmt-config", {"rustfmt-preview"})

    config.unlink()  # Only this test-created file; its prior contents are recorded.
    check("delete-config")
    components("delete-config", set())

    legacy = source / "rust-toolchain"
    legacy.write_text("1.97.1\n")
    check("legacy-file")
    components("legacy-file", set())
    config.write_text(invalid)
    check("legacy-precedence")
    legacy.unlink()  # Only this test-created file; its prior contents are recorded.
    check("remove-legacy-exposes-invalid-toml", 1)
    config.write_text(fmt)
    check("final-repair")
    components("final-repair", {"rustfmt-preview"})
    (root / "result.json").write_text(json.dumps({"passed": True, "scope": "pinned root fixture",
        "performance_claim": False}, indent=2) + "\n")
    print("PASS: component additions, config failure/repair/removal, legacy precedence, source invalidation", flush=True)


if __name__ == "__main__":
    main()
