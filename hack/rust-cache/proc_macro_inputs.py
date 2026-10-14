#!/usr/bin/env python3
"""Reproduce procedural-macro inputs absent from rustc dependency records."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--toolchain", required=True, type=Path)
    args = parser.parse_args()
    root = args.out.resolve()
    if root.is_relative_to(Path.cwd().resolve()):
        parser.error("keep fixture and compiler outputs outside the checkout")
    root.mkdir(exist_ok=False)
    source = root / "source"
    shutil.copytree(Path(__file__).parent / "fixtures" / "proc-macro-inputs", source)
    toolchain = args.toolchain.resolve()
    env = dict(os.environ, RUSTC=str(toolchain / "rustc"), RUSTDOC=str(toolchain / "rustdoc"),
               CARGO_TARGET_DIR=str(root / "target"), CARGO_INCREMENTAL="1")
    for name in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS",
                 "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_BUILD_DIR"):
        env.pop(name, None)
    cargo = str(toolchain / "cargo")

    def run(label, *, fail=False):
        with (root / (label + ".log")).open("w") as output:
            result = subprocess.run([cargo, "test", "--workspace", "--offline"], cwd=source,
                                    env=env, stdout=output, stderr=subprocess.STDOUT)
        if (result.returncode != 0) != fail:
            raise RuntimeError(f"{label}: unexpected exit {result.returncode}; inspect its log")

    def clean_app():
        subprocess.run([cargo, "clean", "-p", "app"], cwd=source, env=env, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    run("prime")
    dependencies = "\n".join(p.read_text() for p in (root / "target/debug/deps").glob("*.d"))
    if "value.txt" in dependencies or "override.txt" in dependencies:
        raise RuntimeError("compiler now tracks the fixture's macro reads; revisit this repro")
    (root / "dep-info.txt").write_text(dependencies)

    data = source / "data/value.txt"
    data.write_text("12\n")
    run("changed-file-stale")
    clean_app()
    run("changed-file-recompiled", fail=True)

    data.write_text("10\n")
    clean_app()
    run("restored-prime")
    override = source / "data/override.txt"
    override.write_text("12\n")
    run("added-file-stale")
    clean_app()
    run("added-file-recompiled", fail=True)
    print("PASS: macro reads and failed existence checks are absent from dep-info; forced rebuilds expose stale results")


if __name__ == "__main__":
    main()
