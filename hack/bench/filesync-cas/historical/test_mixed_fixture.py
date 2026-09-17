#!/usr/bin/env python3
"""Tiny local-fixture tests only: never use Ruff, Docker, engines, or timings."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mixed_fixture as mixed


class SelectionTest(unittest.TestCase):
    def entries(self):
        entries = {f'crates/c{directory:03d}/f{index}.rs': mixed.file_entry(b'original', 0o644)
                   for directory in range(64) for index in range(3)}
        entries[mixed.PROBE] = mixed.file_entry(b'protected', 0o644)
        entries['target/protected'] = mixed.file_entry(b'excluded', 0o644)
        entries['crates/c000/link'] = {'kind': 'symlink', 'mode': 0o777, 'target': 'f0.rs'}
        return entries

    def test_counts_spread_and_protected_paths(self):
        entries = self.entries()
        original = copy.deepcopy(entries)
        plan = mixed.selection(entries, 'cohort1-round1')
        self.assertEqual({kind: len(paths) for kind, paths in plan.items()}, mixed.COUNTS)
        self.assertEqual(plan, mixed.selection(dict(reversed(list(entries.items()))), 'cohort1-round1'))
        self.assertEqual(entries, original)
        names = set(plan['modify'] + plan['delete'] + plan['add'])
        self.assertEqual(len(names), 256)
        self.assertNotIn(mixed.PROBE, names)
        self.assertNotIn('target/protected', names)
        self.assertNotIn('crates/c000/link', names)
        self.assertEqual(len({str(Path(name).parent) for name in plan['add']}), 64)
        self.assertTrue(all(entries[name]['kind'] == 'file' for name in plan['modify'] + plan['delete']))
        self.assertNotEqual(plan['add'], mixed.selection(entries, 'cohort1-round2')['add'])

    def test_rejects_unsafe_tokens_and_small_sources(self):
        for token in ('', '../escape', 'a/b', 'a' * 65, 'UPPER'):
            with self.assertRaises(ValueError):
                mixed.selection(self.entries(), token)
        with self.assertRaises(ValueError):
            mixed.selection({}, 'safe')


class FixtureTest(unittest.TestCase):
    def setUp(self):
        # Only this newly created exact test directory is cleaned by tempfile.
        self.temporary = tempfile.TemporaryDirectory(prefix='mixed-unit-', dir=mixed.ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        for directory in range(64):
            parent = self.source / f'crates/c{directory:03d}'
            parent.mkdir(parents=True)
            for index in range(3):
                path = parent / f'f{index}.rs'
                path.write_bytes(f'original {directory} {index}\n'.encode())
                path.chmod(0o755 if index == 0 else 0o644)
        probe = self.source / mixed.PROBE
        probe.parent.mkdir(parents=True)
        probe.write_bytes(b'protected probe\n')
        excluded = self.source / 'target/excluded'
        excluded.parent.mkdir()
        excluded.write_bytes(b'not part of the import\n')
        (self.source / 'crates/c000/link').symlink_to('f0.rs')
        stamp = 1_700_000_000_000_000_000
        for path in self.source.rglob('*'):
            os.utime(path, ns=(stamp, stamp), follow_symlinks=False)
        os.utime(self.source, ns=(stamp, stamp))
        self.baseline = mixed.snapshot(self.source)
        self.inodes = {name: mixed.identity(self.source / name) for name in self.baseline['manifest']}

    def prepare(self):
        return mixed.MixedFixture.prepare(self.source, self.base, 'unit-round1')

    def assert_restored(self):
        self.assertEqual(mixed.snapshot(self.source), self.baseline)
        self.assertEqual({name: mixed.identity(self.source / name) for name in self.baseline['manifest']}, self.inodes)
        self.assertEqual((self.source / 'target/excluded').read_bytes(), b'not part of the import\n')

    def test_prepare_is_read_only_then_exact_diff_and_reopen_restore(self):
        fixture = self.prepare()
        self.assert_restored()
        fixture.apply()
        fixture.verify_applied()
        before, after = self.baseline['manifest'], fixture.expected['manifest']
        self.assertEqual(len(before.keys() - after.keys()), 64)
        self.assertEqual(len(after.keys() - before.keys()), 64)
        self.assertEqual(sum(before[name] != after[name] for name in before.keys() & after.keys()), 128)
        self.assertEqual(before[mixed.PROBE], after[mixed.PROBE])
        reopened = mixed.MixedFixture.open(fixture.backup)
        reopened.restore()
        reopened.restore()  # Idempotent, while retaining staged/used evidence.
        self.assert_restored()
        self.assertTrue((fixture.backup / 'plan.json').exists())

    def test_interruption_after_original_rename_is_recoverable(self):
        fixture = self.prepare()
        rename = mixed.MixedFixture.move
        calls = 0

        def interrupt(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt('synthetic interruption after first atomic rename')
            rename(source, destination)

        with patch.object(mixed.MixedFixture, 'move', staticmethod(interrupt)):
            with self.assertRaises(KeyboardInterrupt):
                fixture.apply()
        mixed.MixedFixture.open(fixture.backup).restore()
        self.assert_restored()

    def test_unrelated_edits_are_not_overwritten(self):
        fixture = self.prepare()
        fixture.apply()
        path = self.source / mixed.PROBE
        path.write_bytes(b'external change\n')
        with self.assertRaisesRegex(ValueError, 'unrelated source change'):
            fixture.restore()
        self.assertEqual(path.read_bytes(), b'external change\n')
        # Undo only this test's explicit external edit before normal recovery.
        path.write_bytes(b'protected probe\n')
        os.utime(path, ns=(self.baseline['mtime_ns'][mixed.PROBE],) * 2)
        fixture.restore()
        self.assert_restored()


if __name__ == '__main__':
    unittest.main()
