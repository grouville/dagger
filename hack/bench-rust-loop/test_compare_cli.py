"""Local-only regression tests for paired CLI configuration and accounting."""

import ast
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("compare-cli.py")


class CompareCLITest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="test-compare-cli-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workdir = self.root / "workspace"
        self.workdir.mkdir()
        self.binaries = {}
        # These executables do not invoke Dagger: inspect only the environment
        # and command they receive. Keep every generated artifact in this
        # test's temporary directory, including the harness's output directory.
        source = f"#!{sys.executable}\n" + """\
import json
import os
import sys
print(json.dumps({
    "engine": os.environ.get("DAGGER_ENGINE"),
    "sentinel": os.environ.get("COMPARE_CLI_TEST_SENTINEL"),
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
}))
"""
        for side in ("before", "after"):
            binary = self.root / f"{side}-cli"
            binary.write_text(source)
            binary.chmod(0o755)
            self.binaries[side] = binary

    def run_comparison(self, *options, inherited_engine="container://inherited", samples=2):
        env = os.environ.copy()
        env["TMPDIR"] = str(self.root)
        env["COMPARE_CLI_TEST_SENTINEL"] = "preserved"
        if inherited_engine is None:
            env.pop("DAGGER_ENGINE", None)
        else:
            env["DAGGER_ENGINE"] = inherited_engine
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--before", str(self.binaries["before"]),
                "--after", str(self.binaries["after"]),
                "--workdir", str(self.workdir),
                "--samples", str(samples),
                *options, "--", "check", "rust:check",
            ],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        output = Path(lines[0])
        self.assertTrue(output.is_relative_to(self.root), output)
        metadata = json.loads((output / "metadata.json").read_text())
        records = [json.loads(line) for line in (output / "processes.jsonl").read_text().splitlines()]
        with (output / "timings.csv").open(newline="") as file:
            timings = list(csv.DictReader(file))
        logs = {record["label"]: json.loads((output / f'{record["label"]}.log').read_text())
                for record in records}
        summaries = {side: ast.literal_eval(lines[index].removeprefix(side + " "))
                     for index, side in enumerate(("before", "after"), start=1)}
        return metadata, records, timings, logs, summaries

    def assert_child_engines(self, logs, engines):
        for label, child in logs.items():
            with self.subTest(label=label):
                side = label.split("-", 1)[0]
                self.assertEqual(child["engine"], engines[side])
                self.assertEqual(child["sentinel"], "preserved")
                self.assertEqual(child["argv"], ["check", "rust:check"])
                self.assertEqual(child["cwd"], str(self.workdir))

    def test_engine_overrides_are_independent_and_recorded(self):
        metadata, _, _, logs, _ = self.run_comparison(
            "--before-engine", "container://baseline",
            "--after-engine", "container://candidate",
        )
        engines = {"before": "container://baseline", "after": "container://candidate"}
        self.assert_child_engines(logs, engines)
        self.assertEqual(metadata["engines"], engines)
        self.assertEqual(metadata["engine"], "container://inherited")
        self.assertEqual(metadata["command"], ["check", "rust:check"])
        for side, binary in self.binaries.items():
            self.assertEqual(metadata["binary_sha256"][side], hashlib.sha256(binary.read_bytes()).hexdigest())

    def test_one_override_preserves_other_side_inheritance(self):
        for overridden in ("before", "after"):
            with self.subTest(overridden=overridden):
                metadata, _, _, logs, _ = self.run_comparison(
                    f"--{overridden}-engine", "container://override", samples=1,
                )
                engines = dict.fromkeys(("before", "after"), "container://inherited")
                engines[overridden] = "container://override"
                self.assert_child_engines(logs, engines)
                self.assertEqual(metadata["engines"], engines)
                self.assertEqual(metadata["engine"], "container://inherited")

    def test_no_override_preserves_inherited_or_unset_engine(self):
        for inherited in ("container://inherited", None):
            with self.subTest(inherited=inherited):
                metadata, _, _, logs, _ = self.run_comparison(inherited_engine=inherited, samples=1)
                engines = dict.fromkeys(("before", "after"), inherited)
                self.assert_child_engines(logs, engines)
                self.assertEqual(metadata["engines"], engines)
                self.assertEqual(metadata["engine"], inherited)

    def test_explicit_empty_override_does_not_inherit(self):
        metadata, _, _, logs, _ = self.run_comparison("--before-engine", "", samples=1)
        engines = {"before": "", "after": "container://inherited"}
        self.assert_child_engines(logs, engines)
        self.assertEqual(metadata["engines"], engines)

    def test_alternating_order_retains_but_excludes_warmup(self):
        metadata, records, timings, _, summaries = self.run_comparison(samples=3)
        expected = ["before-0", "after-0", "after-1", "before-1",
                    "before-2", "after-2", "after-3", "before-3"]
        self.assertEqual([record["label"] for record in records], expected)
        self.assertEqual([f'{row["side"]}-{row["sample"]}' for row in timings], expected)
        self.assertEqual(metadata["samples"], 3)
        self.assertEqual(metadata["warmup_pairs"], 1)
        self.assertEqual([row["warmup"] for row in timings], ["True"] * 2 + ["False"] * 6)
        for side in ("before", "after"):
            measured = [float(row["milliseconds"]) for row in timings
                        if row["side"] == side and row["warmup"] == "False"]
            self.assertEqual(summaries[side], {
                "median_ms": statistics.median(measured),
                "min_ms": min(measured), "max_ms": max(measured),
            })
        self.assertTrue(all(record["exit_code"] == 0 for record in records))


if __name__ == "__main__":
    unittest.main()
