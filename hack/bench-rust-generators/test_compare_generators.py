"""Pure-Python guards only: no Docker, Dagger, Cargo, network or subprocesses."""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("compare_generators", Path(__file__).with_name("compare-generators.py"))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class CompareGeneratorGuards(unittest.TestCase):
    def archive(self, identifier, suffix=".a", object_name_reference=False):
        names = [f"prototype_library-9a6f7ae904368f6c.{unit}.{identifier}.rcgu.o"
                 for unit in ("codegenone", "codegentwo")]
        if suffix == ".rlib":
            rows = [("lib.rmeta", b"unchanged Rust metadata"),
                    ("lib.rmeta-link", b"ELF link metadata:" + names[0].encode() + b":end"),
                    (names[0], b"object code and debug data")]
            codegen_names = names[:1]
        else:
            rows = [(names[0], b"object code" + (names[0].encode() if object_name_reference else b"")),
                    (names[1], b"second object code"), ("stdlib.o", b"unchanged library")]
            codegen_names = names
        members = [dict(name=name, header=["rw-r--r--", "0/0", str(len(payload)), "Jan", "1", "00:00", "1970"],
                        payload=payload) for name, payload in rows]
        # Deliberately synthetic data: pure guard tests, not a homemade ar
        # reader/writer. inspect_archive's maintained-reader boundary is mocked
        # separately below. Raw index/padding bytes must still be checked.
        raw = b"!<arch>\nINDEX\0" + b"/\n".join(name.encode() for name in codegen_names)
        raw += b"\nHEADERS\0" + b"".join(member["payload"] for member in members) + b"PADDING"
        return dict(raw=raw, members=members)

    def test_strict_archive_identifier_equivalence(self):
        for suffix in (".a", ".rlib"):
            with self.subTest(suffix=suffix):
                actual, reference = self.archive("0aaaaaa", suffix), self.archive("0bbbbbb", suffix)
                result = bench.archive_equivalence(actual, reference, suffix)
                self.assertTrue(result["equivalent"])
                self.assertFalse(result["raw_bytes_equal"])
                self.assertEqual(sum(not row["raw_payload_equal"] for row in result["members"]), suffix == ".rlib")
                self.assertNotEqual(actual["raw"], reference["raw"])

    def test_archive_object_change_never_normalized(self):
        actual, reference = self.archive("0aaaaaa"), self.archive("0bbbbbb")
        actual["members"][0]["payload"] = b"altered code"
        with self.assertRaisesRegex(ValueError, "member payload differs"):
            bench.archive_equivalence(actual, reference, ".a")
        # Even a full allowed filename inside object bytes is not normalized.
        with self.assertRaisesRegex(ValueError, "member payload differs"):
            bench.archive_equivalence(self.archive("0aaaaaa", object_name_reference=True),
                                      self.archive("0bbbbbb", object_name_reference=True), ".a")

    def test_archive_may_reuse_one_codegen_member_identifier(self):
        actual, reference = self.archive("0aaaaaa"), self.archive("0bbbbbb")
        old, new = actual["members"][1]["name"], reference["members"][1]["name"]
        actual["members"][1]["name"] = new
        actual["raw"] = actual["raw"].replace(old.encode(), new.encode())
        result = bench.archive_equivalence(actual, reference, ".a")
        self.assertEqual(len(result["renamed_members"]), 1)

    def test_archive_index_padding_and_extra_bytes_rejected(self):
        for old, new in ((b"INDEX", b"index"), (b"PADDING", b"padding"), (b"PADDING", b"PADDINGextra")):
            with self.subTest(old=old, new=new):
                actual, reference = self.archive("0aaaaaa"), self.archive("0bbbbbb")
                actual["raw"] = actual["raw"].replace(old, new)
                with self.assertRaisesRegex(ValueError, "archive bytes differ"):
                    bench.archive_equivalence(actual, reference, ".a")

    def test_archive_unknown_names_order_and_collisions_rejected(self):
        for change in ("unknown", "crate hash", "order", "collision"):
            with self.subTest(change=change):
                actual, reference = self.archive("0aaaaaa"), self.archive("0bbbbbb")
                if change == "unknown":
                    actual["members"][-1]["name"] = "other-library.o"
                elif change == "crate hash":
                    actual["members"][0]["name"] = actual["members"][0]["name"].replace("9a6f", "1234")
                elif change == "order":
                    actual["members"].reverse()
                else:
                    for archive in (actual, reference):
                        duplicate = copy.deepcopy(archive["members"][0])
                        duplicate["name"] = duplicate["name"].replace(".0", ".1")
                        archive["members"].append(duplicate)
                with self.assertRaisesRegex(ValueError, "names/order differ or collide"):
                    bench.archive_equivalence(actual, reference, ".a")

    def test_archive_headers_and_unknown_rmeta_link_changes_rejected(self):
        actual, reference = self.archive("0aaaaaa"), self.archive("0bbbbbb")
        actual["members"][0]["header"][0] = "rw-------"
        with self.assertRaisesRegex(ValueError, "headers differ"):
            bench.archive_equivalence(actual, reference, ".a")
        actual, reference = self.archive("0aaaaaa", ".rlib"), self.archive("0bbbbbb", ".rlib")
        actual["members"][1]["payload"] = actual["members"][1]["payload"].replace(b"ELF", b"BAD")
        with self.assertRaisesRegex(ValueError, "metadata differs beyond"):
            bench.archive_equivalence(actual, reference, ".rlib")

    def test_archive_name_reference_counts_are_exact(self):
        actual, reference = self.archive("0aaaaaa"), self.archive("0bbbbbb")
        actual["raw"] += actual["members"][0]["name"].encode()
        with self.assertRaisesRegex(ValueError, "unexpected compiler-name occurrences"):
            bench.archive_equivalence(actual, reference, ".a")

    def test_archive_reader_uses_maintained_ar_table_and_payload(self):
        expected = self.archive("0aaaaaa")
        outputs = {
            "t": "\n".join(row["name"] for row in expected["members"]).encode() + b"\n",
            "tv": "\n".join(" ".join(row["header"]) + " " + row["name"] for row in expected["members"]).encode() + b"\n",
            "p": b"".join(row["payload"] for row in expected["members"]),
        }
        with tempfile.TemporaryDirectory(prefix="generator-archive-guard-") as directory:
            path = Path(directory) / "fixture.a"
            path.write_bytes(expected["raw"])
            def read(command, **kwargs):
                self.assertEqual(command, ["/mock/ar", command[1], str(path)])
                self.assertEqual(kwargs["env"]["LC_ALL"], "C")
                return SimpleNamespace(stdout=outputs[command[1]], stderr=b"")
            with patch.object(bench.subprocess, "run", side_effect=read) as mock:
                self.assertEqual(bench.inspect_archive(path, "/mock/ar"), expected)
                self.assertEqual(mock.call_count, 3)
                outputs["p"] += b"extra"
                with self.assertRaisesRegex(ValueError, "sizes do not match"):
                    bench.inspect_archive(path, "/mock/ar")

    def test_archive_comparison_keeps_raw_hashes_and_failure_evidence(self):
        name = "debug/libprototype_library.a"
        archives = {side: self.archive(identifier) for side, identifier in zip(bench.SIDES, ("0aaaaaa", "0bbbbbb", "0cccccc"))}
        roots = {side: Path("/mock") / side for side in bench.SIDES}
        def manifests():
            return {side: {name: dict(kind="file", bytes=len(value["raw"]), sha256=hashlib.sha256(value["raw"]).hexdigest(), mode=0o644)}
                    for side, value in archives.items()}
        with patch.object(bench, "inspect_archive", side_effect=lambda path, ar: archives[path.parts[2]]):
            recorded = manifests()
            audits = []
            self.assertEqual(bench.compare_artifacts(recorded, roots, audits), [])
            self.assertEqual(recorded, manifests())
            self.assertTrue(all(row["equivalent"] and not row["raw_bytes_equal"] for row in audits))
            archives["before"]["raw"] = archives["before"]["raw"].replace(b"INDEX", b"index")
            audits = []
            with self.assertRaisesRegex(ValueError, "archive bytes differ"):
                bench.compare_artifacts(manifests(), roots, audits)
            self.assertFalse(audits[0]["equivalent"])
            self.assertIn("archive bytes differ", audits[0]["error"])

    def test_explicit_execute_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            bench.parse_args(["--dagger", "/unused", "--before-engine", "container://before", "--after-engine", "container://after"])

    def test_distinct_engines_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            bench.parse_args(["--execute", "--dagger", "/unused", "--before-engine", "container://same", "--after-engine", "container://same"])

    def test_pilot_default(self):
        args = bench.parse_args(["--execute", "--dagger", "/unused", "--before-engine", "container://b", "--after-engine", "container://a"])
        self.assertEqual(args.samples, 3)
        self.assertEqual(args.engine_readiness, "asymmetric-or-unknown")

    def test_novel_edit_and_anchor(self):
        original = 'fn main() { println!("app-v1: {}", value); }'
        self.assertNotEqual(bench.edited(original, "application", "nonce-1"), bench.edited(original, "application", "nonce-2"))
        with self.assertRaises(ValueError):
            bench.edited(original + original, "application", "nonce")
        with self.assertRaises(ValueError):
            bench.edited(original, "application", 'bad"token')

    def test_balanced_six_orders(self):
        self.assertEqual(len(set(bench.ORDERS)), 6)
        for position in range(3):
            for side in bench.SIDES:
                self.assertEqual(sum(order[position] == side for order in bench.ORDERS), 2)

    def messages(self):
        rows = []
        for path in sorted(bench.OUTPUTS):
            rows.append(dict(reason="compiler-artifact", package_id="member", target=dict(kind=["bin"], name=path),
                             profile=dict(opt_level="0", debuginfo=2), fresh=True, filenames=["/out/" + path]))
        rows.append(dict(reason="build-finished", success=True))
        return rows

    def test_fresh_artifacts_are_not_discarded(self):
        parsed = bench.cargo_artifacts("non-JSON compiler text\n" + "\n".join(map(json.dumps, self.messages())), {"member"})
        self.assertEqual(set(parsed), bench.OUTPUTS)
        self.assertTrue(all(row["fresh"] for row in parsed.values()))

    def test_failed_or_missing_completion_rejected(self):
        for rows in (self.messages()[:-1], self.messages()[:-1] + [dict(reason="build-finished", success=False)]):
            with self.assertRaises(ValueError):
                bench.cargo_artifacts("\n".join(map(json.dumps, rows)), {"member"})

    def test_bad_output_path_rejected(self):
        rows = self.messages()
        rows[0]["filenames"] = ["/out/../escape"]
        with self.assertRaises(ValueError):
            bench.cargo_artifacts("\n".join(map(json.dumps, rows)), {"member"})

    def test_mode_bug_recorded_but_bytes_fail(self):
        base = dict(kind="file", bytes=10, sha256="abc", mode=0o755)
        manifests = {side: {"debug/app": dict(base)} for side in bench.SIDES}
        manifests["before"]["debug/app"]["mode"] = 0o777
        discrepancies = bench.compare_artifacts(manifests)
        self.assertTrue(discrepancies[0]["known_baseline_bug"])
        manifests["before"]["debug/app"]["sha256"] = "different"
        with self.assertRaises(ValueError):
            bench.compare_artifacts(manifests)

    def test_cleanup_requires_both_id_and_label(self):
        identity = dict(Id="expected-id", Config=dict(Labels={bench.OWNER_LABEL: "owned"}))
        bench.verify_native_owner(identity, "expected-id", "owned")
        for container_id, owner in (("other-id", "owned"), ("expected-id", "other-owner")):
            with self.assertRaises(ValueError):
                bench.verify_native_owner(identity, container_id, owner)

    def test_only_known_mode_discrepancies_can_pass(self):
        bench.validate_mode_discrepancies([dict(known_baseline_bug=True)])
        with self.assertRaises(ValueError):
            bench.validate_mode_discrepancies([dict(known_baseline_bug=False)])

    def test_generator_git_setup_is_recorded_per_workspace(self):
        calls = []
        bench.initialize_generator_workspaces(lambda *args: calls.append(args))
        self.assertEqual(calls, [
            ("setup-before-git-init", ["git", "init", "--quiet"], "before"),
            ("setup-after-git-init", ["git", "init", "--quiet"], "after"),
        ])

    def test_git_environment_isolated_without_recording_sensitive_values(self):
        inherited = {key: "sensitive-value" for key in (
            "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_TEMPLATE_DIR",
            "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0",
            "GIT_CONFIG_VALUE_0", "GIT_CONFIG_PARAMETERS", "GIT_TRACE", "GIT_EXEC_PATH", "git_dir")}
        preserved = dict(PATH="/tools", CARGO_TARGET_DIR="/out", RUSTFLAGS="unchanged", OTHER="unchanged")
        inherited.update(preserved)
        original = inherited.copy()
        clean, policy = bench.isolated_git_environment(inherited)
        self.assertEqual(inherited, original)
        self.assertEqual({key: clean[key] for key in preserved}, preserved)
        self.assertEqual({key: value for key, value in clean.items() if key.upper().startswith("GIT_")},
                         dict(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=bench.os.devnull, GIT_TERMINAL_PROMPT="0"))
        self.assertEqual(policy["inherited_variables_removed"], len(inherited) - len(preserved))
        self.assertNotIn("sensitive-value", json.dumps(policy))
        self.assertNotIn("sensitive-value", json.dumps(clean))

    def test_frozen_module_git_root_initialized_verified_and_recorded(self):
        with tempfile.TemporaryDirectory(prefix="generator-module-git-guard-") as directory:
            ancestor = Path(directory)
            (ancestor / ".git").mkdir()  # Existing ancestor must not become this module's root.
            frozen = ancestor / "module"
            frozen.mkdir()
            (frozen / "main.dang").write_text("unchanged compiler/module source")
            (frozen / "dagger-module.toml").write_text("unchanged module configuration")
            hashes = {name: bench.digest(frozen / name) for name in ("main.dang", "dagger-module.toml")}
            calls = []
            def process(label, command, **kwargs):
                calls.append((label, command, kwargs))
                log = ancestor / (label + ".log")
                if label == "setup-module-git-init":
                    (frozen / ".git").mkdir()
                    log.write_text("")
                else:
                    log.write_text(str(frozen.resolve()) + "\n")
                return log
            with patch.object(bench.subprocess, "run", side_effect=AssertionError("no real Git subprocess allowed")):
                self.assertEqual(bench.initialize_frozen_module_git(process, frozen), str(frozen.resolve()))
            self.assertEqual(calls, [
                ("setup-module-git-init", ["git", "init", "--quiet"], dict(cwd=frozen)),
                ("setup-module-git-root", ["git", "-C", str(frozen), "rev-parse", "--show-toplevel"], dict(cwd=frozen)),
            ])
            self.assertEqual(hashes, {name: bench.digest(frozen / name) for name in hashes})
            self.assertTrue((ancestor / ".git").is_dir())

    def test_frozen_module_rejects_preexisting_git_state(self):
        for kind in ("directory", "file", "dangling-symlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(prefix="generator-module-git-guard-") as directory:
                frozen = Path(directory)
                git = frozen / ".git"
                if kind == "directory":
                    git.mkdir()
                elif kind == "file":
                    git.write_text("gitdir: /unrelated/worktree")
                else:
                    git.symlink_to(frozen / "missing")
                with patch.object(bench.subprocess, "run", side_effect=AssertionError("no real Git subprocess allowed")):
                    with self.assertRaisesRegex(ValueError, "preexisting frozen module Git state"):
                        bench.initialize_frozen_module_git(lambda *args, **kwargs: self.fail("setup must not run"), frozen)

    def test_frozen_module_rejects_redirected_root_and_retains_result(self):
        for result in ("ancestor", "relative", "multiple"):
            with self.subTest(result=result), tempfile.TemporaryDirectory(prefix="generator-module-git-guard-") as directory:
                ancestor = Path(directory)
                frozen = ancestor / "module"
                frozen.mkdir()
                recorded = ancestor / "setup-module-git-root.log"
                content = str(ancestor) if result == "ancestor" else ("relative/path" if result == "relative" else str(frozen) + "\nextra")
                def process(label, command, **kwargs):
                    if label == "setup-module-git-init":
                        (frozen / ".git").mkdir()
                    else:
                        recorded.write_text(content + "\n")
                    return recorded
                with self.assertRaisesRegex(ValueError, "frozen module Git root"):
                    bench.initialize_frozen_module_git(process, frozen)
                self.assertEqual(recorded.read_text(), content + "\n")

    def test_frozen_module_rejects_linked_git_directory_after_init(self):
        with tempfile.TemporaryDirectory(prefix="generator-module-git-guard-") as directory:
            ancestor = Path(directory)
            (ancestor / ".git").mkdir()
            frozen = ancestor / "module"
            frozen.mkdir()
            calls = []
            def process(label, command, **kwargs):
                calls.append(label)
                (frozen / ".git").symlink_to(ancestor / ".git", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "own real directory"):
                bench.initialize_frozen_module_git(process, frozen)
            self.assertEqual(calls, ["setup-module-git-init"])

    def test_artifact_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory(prefix="generator-guard-test-") as directory:
            root = Path(directory)
            (root / "real").mkdir()
            (root / "real/app").write_bytes(b"fixture")
            (root / "linked").symlink_to("real", target_is_directory=True)
            with self.assertRaises(ValueError):
                bench.artifact_manifest(root, {"linked/app"}, exact=False)


if __name__ == "__main__":
    unittest.main()
