#!/usr/bin/env python3
"""Measure and verify fresh discovery after edits to a disposable Go fixture.

Create the fixture with bench-artifact-discovery-fixture.py --go-module first.
This temporarily edits its test source and adds a module, restores both in a
finally block, and checks every discovered (module, test) key after each edit.
Each phase starts a new CLI process. The engine and its caches remain running.
"""

import argparse
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--surface", choices=["expanded-checks", "default-checks", "collection-modules", "collection-tests", "artifact-checks"],
                        default="expanded-checks", help="user-facing discovery command to measure")
    parser.add_argument("--format", choices=["cli", "table"], default="cli",
                        help="listing format; table uses the default command with no format flag")
    parser.add_argument("--from-workspace", action="store_true",
                        help="run in the fixture directory without --workspace, like 'cd project; dagger ...'")
    parser.add_argument("--wcprof-url", help="save a separate profile of each edit, without a priming query")
    parser.add_argument("--budget-ms", type=float,
                        help="fail after collecting all phases if any command exceeds this end-to-end budget")
    args = parser.parse_args()
    args.workspace = args.workspace.resolve()
    args.output = args.output.resolve()
    if args.budget_ms is not None and args.budget_ms <= 0:
        parser.error("--budget-ms must be positive")
    marker = args.workspace / ".discovery-benchmark-fixture"
    if not marker.is_file() or marker.read_text() != "go\n":
        parser.error("workspace must be a disposable generated Go benchmark fixture")
    source = args.workspace / "m0/pkg00/sample_test.go"
    original = source.read_bytes()
    config = args.workspace / "m0/go.mod"
    original_config = config.read_bytes()
    added = args.workspace / "invalidation-module"
    if added.exists() or b"func TestCase0_0(" not in original:
        parser.error("fixture has unexpected existing edits")
    runner = Path(__file__).with_name("bench-artifact-discovery.py")
    phases = []
    iteration = uuid.uuid4().hex
    edit_marker = f"\n// discovery benchmark iteration {iteration}\n".encode()
    commands = {
        "expanded-checks": ["check", "-l", "--all", "--generated=false", "go/modules/tests/run"],
        "default-checks": ["check", "-l"],
        "collection-modules": ["list", "go-modules"],
        "collection-tests": ["list", "go-tests"],
        "artifact-checks": ["list", "checks", "go/modules/tests/run"],
    }
    listing = args.surface.startswith("collection-") or args.surface == "artifact-checks"
    if listing and args.format != "table":
        commands[args.surface] += ["-f", args.format]
    expands_tests = args.surface in ("expanded-checks", "collection-tests", "artifact-checks")

    def run(phase, expected=None):
        dest = args.output / phase
        profile_args = []
        if args.wcprof_url:
            url = args.wcprof_url.rstrip("/")
            # Initialize/drain the recorder through debug HTTP, which does not
            # evaluate discovery and accidentally warm the edited inputs.
            with urllib.request.urlopen(urllib.request.Request(url + "/debug/wcprof/enabled", data=b"on"), timeout=10) as response:
                response.read()
            with urllib.request.urlopen(url + "/debug/wcprof/dump", timeout=60) as response:
                while response.read(1024 * 1024):
                    pass
            with urllib.request.urlopen(urllib.request.Request(url + "/debug/wcprof/enabled", data=b"off"), timeout=10) as response:
                response.read()
            profile_args = ["--wcprof-url", url, "--cold-profile"]
        subprocess.run([
            sys.executable, str(runner), "--runs", "1", "--warmups", "0",
            "--output", str(dest), *profile_args, "--", str(args.cli.resolve()),
            "--engine", args.engine,
            *([] if args.from_workspace else ["--workspace", str(args.workspace)]),
            *commands[args.surface],
        ], check=True, cwd=args.workspace if args.from_workspace else None)
        output = (dest / "run-0.out").read_bytes()
        keys = []
        lines = output.decode().splitlines()
        if listing and args.format == "table":
            columns = re.split(r" {2,}", lines.pop(0).strip())
        for line in lines:
            if args.surface == "default-checks":
                # Schema-path listing deliberately leaves dimensions collapsed.
                keys.append((line, ""))
                continue
            if listing and args.format == "table":
                # This generated fixture has simple keys without spaces. Its
                # repeated test names require the parent module column too.
                flags = dict(zip((name.lower() for name in columns), re.split(r" {2,}", line.strip())))
            else:
                flags = dict(word[2:].split("=", 1) for word in shlex.split(line)
                             if word.startswith("--") and "=" in word)
            keys.append((flags["go-module"], flags.get("go-test", "")))
        if expected is not None and args.surface in ("collection-modules", "collection-tests", "artifact-checks"):
            # Artifact/collection listings order links lexically, whereas
            # expanded check listings retain traversal order. Renames move rows.
            expected = sorted(expected)
        if expected is not None and keys != expected:
            raise AssertionError(f"{phase}: stale, missing, reordered, or unexpected keys")
        result = json.loads((dest / "results.json").read_text())
        phases.append({"phase": phase, "surface": args.surface, "format": args.format, "iteration": iteration, "cwd": result["cwd"], "seconds": result["median_seconds"],
                       "keys": len(keys), "stdout_sha256": result["runs"][0]["stdout_sha256"]})
        return output, keys

    try:
        # The fixture generator defines these keys independently of discovery.
        # Do not bless an incomplete first listing as the expected baseline.
        expected_baseline = None
        if expands_tests:
            expected_baseline = [(f"m{module}", f"TestCase{package}_{test}")
                                 for module in range(8) for package in range(16) for test in range(8)]
        elif args.surface == "collection-modules":
            expected_baseline = [(f"m{module}", "") for module in range(8)]
        baseline_output, baseline = run("unchanged", expected_baseline)
        source.write_bytes(original + edit_marker)
        output, _ = run("content-edit", baseline)
        if output != baseline_output:
            raise AssertionError("content-only edit changed listing bytes")

        source.write_bytes(original)
        config.write_bytes(original_config.replace(b"go 1.26.1", b"go 1.26.0") + edit_marker)
        output, _ = run("module-config-edit", baseline)
        if output != baseline_output:
            raise AssertionError("Go patch version edit changed listing bytes")
        config.write_bytes(original_config)

        source.write_bytes(original.replace(b"func TestCase0_0(", b"func TestInvalidated(") + edit_marker)
        renamed = [(mod, "TestInvalidated" if mod == "m0" and name == "TestCase0_0" else name)
                   for mod, name in baseline]
        run("rename-test", renamed)

        source.write_bytes(original + b"\nfunc TestAdded(t *testing.T) {}\n" + edit_marker)
        with_test = baseline
        if expands_tests:
            insert_at = baseline.index(("m0", "TestCase0_7")) + 1
            with_test = baseline[:insert_at] + [("m0", "TestAdded")] + baseline[insert_at:]
        run("add-test", with_test)

        source.write_bytes(original)
        added.mkdir()
        (added / "go.mod").write_bytes(b"module example.com/invalidation\n\ngo 1.26.1\n" + edit_marker)
        (added / "new_test.go").write_text(
            'package invalidation\nimport "testing"\nfunc TestNewModule(t *testing.T) {}\n')
        # Module roots are lexical; this new module precedes m0.
        with_module = baseline
        if args.surface != "default-checks":
            with_module = [("invalidation-module", "TestNewModule" if expands_tests else "")] + baseline
        run("add-module", with_module)

        shutil.rmtree(added)
        output, _ = run("remove-and-restore", baseline)
        if output != baseline_output:
            raise AssertionError("restored fixture changed listing bytes")
        (args.output / "invalidation.json").write_text(json.dumps(phases, indent=2) + "\n")
        if args.budget_ms is not None:
            failures = [phase for phase in phases if phase["seconds"] * 1000 > args.budget_ms]
            budget = {"budget_ms": args.budget_ms, "passed": not failures,
                      "over_budget": [phase["phase"] for phase in failures]}
            (args.output / "budget.json").write_text(json.dumps(budget, indent=2) + "\n")
            if failures:
                raise SystemExit(f"{len(failures)} phases exceeded {args.budget_ms:g} ms; see budget.json")
    finally:
        source.write_bytes(original)
        config.write_bytes(original_config)
        if added.exists():
            shutil.rmtree(added)


if __name__ == "__main__":
    main()
