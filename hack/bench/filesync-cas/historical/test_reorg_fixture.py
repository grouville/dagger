#!/usr/bin/env python3
"""Owned synthetic-fixture tests only; no Ruff, Docker, engines or measurements."""
import copy
import os
from pathlib import Path, PurePosixPath
import tempfile
import unittest
from unittest.mock import patch

import reorg_fixture as reorg


def synthetic_entries():
    entries = {}

    def add(name, item):
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.':
                entries.setdefault(str(parent), {'kind': 'directory', 'mode': 0o755})
        entries[name] = item

    for crate in range(8):
        base = f'crates/c{crate:02d}'
        for index in range(32):
            name = f'{base}/loose{index:02d}.rs'
            add(name, reorg.file_entry((name + '\n').encode(), 0o644))
        for branch in ('alpha', 'beta', 'deep/gamma', 'deeper/layer/delta'):
            for index in range(3):
                name = f'{base}/{branch}/f{index}.py'
                add(name, reorg.file_entry((name + '\n').encode(), 0o755 if index == 0 else 0o644))
        add(f'{base}/alpha/link', {'kind': 'symlink', 'mode': 0o777, 'target': 'f0.py'})
        for index in range(8):
            add(f'{base}/landing/d{index:02d}', {'kind': 'directory', 'mode': 0o755})
    add(reorg.PROBE, reorg.file_entry((reorg.PROBE + '\n').encode(), 0o644))
    for index in range(3):
        name = f'crates/c00/protected/inner/f{index}.rs'
        add(name, reorg.file_entry((name + '\n').encode(), 0o644))
    return entries


class SelectionTest(unittest.TestCase):
    def test_deterministic_disjoint_multidepth_plan(self):
        entries = synthetic_entries()
        before = copy.deepcopy(entries)
        protected = ['crates/c00/protected/target']
        actions = reorg.selection(entries, 'cohort1-round1', protected)
        self.assertEqual(actions, reorg.selection(dict(reversed(list(entries.items()))), 'cohort1-round1', protected))
        self.assertEqual(entries, before)
        self.assertEqual(dict(reorg.Counter(action['kind'] for action in actions)), reorg.COUNTS)
        directories = [action for action in actions if action['kind'] == 'directory']
        self.assertGreaterEqual(len({len(PurePosixPath(action['source']).parts) for action in directories}), 2)
        self.assertGreaterEqual(len({reorg.group(action['source']) for action in directories}), 2)
        for index, action in enumerate(directories):
            self.assertFalse(reorg.within(reorg.PROBE, action['source']))
            self.assertFalse(any(reorg.within(path, action['source']) for path in protected))
            for other in directories[index + 1:]:
                self.assertFalse(reorg.within(action['source'], other['source']) or reorg.within(other['source'], action['source']))
        local = sum(PurePosixPath(action['source']).parent == PurePosixPath(action['destination']).parent for action in directories)
        self.assertEqual(local, 12)
        for action in actions:
            if action['kind'] in ('file', 'delete'):
                self.assertNotEqual(action['source'], reorg.PROBE)
                self.assertFalse(any(reorg.within(action['source'], directory['source']) for directory in directories))
            if action['kind'] == 'file':
                self.assertNotEqual(PurePosixPath(action['source']).parent, PurePosixPath(action['destination']).parent)
            if action['destination']:
                self.assertNotIn(action['destination'], entries)
        self.assertNotEqual(actions, reorg.selection(entries, 'cohort1-round2', protected))

    def test_invalid_inputs_fail_before_mutation(self):
        for token in ('', '../escape', 'UPPER', 'x' * 65):
            with self.assertRaises(ValueError):
                reorg.selection(synthetic_entries(), token)
        with self.assertRaises(ValueError):
            reorg.selection({}, 'valid')


class ReorgTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='reorg-unit-', dir=reorg.ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        entries = synthetic_entries()
        for name, entry in sorted(entries.items(), key=lambda pair: (len(PurePosixPath(pair[0]).parts), pair[0])):
            path = self.source / name
            if entry['kind'] == 'directory':
                path.mkdir()
            elif entry['kind'] == 'symlink':
                path.symlink_to(entry['target'])
            else:
                path.write_bytes((name + '\n').encode())
                path.chmod(entry['mode'])
        self.excluded = self.source / 'crates/c00/protected/target/data'
        self.excluded.parent.mkdir()
        self.excluded.write_bytes(b'excluded payload\n')
        stamp = 1_700_000_000_000_000_000
        for path in self.source.rglob('*'):
            os.utime(path, ns=(stamp, stamp), follow_symlinks=False)
        os.utime(self.source, ns=(stamp, stamp))
        self.baseline = reorg.snapshot(self.source)
        self.inodes = {name: reorg.identity(self.source / name) for name in self.baseline['manifest']}
        self.excluded_id = reorg.identity(self.excluded)

    def prepare(self):
        return reorg.ReorgFixture.prepare(self.source, self.base, 'test-round1')

    def assert_restored(self):
        self.assertEqual(reorg.snapshot(self.source), self.baseline)
        self.assertEqual({name: reorg.identity(self.source / name) for name in self.baseline['manifest']}, self.inodes)
        self.assertEqual(self.excluded.read_bytes(), b'excluded payload\n')
        self.assertEqual(reorg.identity(self.excluded), self.excluded_id)
        self.assertEqual(self.excluded.stat().st_mtime_ns, 1_700_000_000_000_000_000)

    def test_apply_exact_mapping_and_finally_restore(self):
        fixture = self.prepare()
        self.assert_restored()
        original = self.baseline['manifest']
        with fixture.applied():
            fixture.verify_applied()
            self.assertEqual(len(fixture.expected['manifest']), len(original))
            self.assertEqual(fixture.expected['manifest'][reorg.PROBE], original[reorg.PROBE])
            moved = []
            for action in fixture.record['actions']:
                if action['kind'] in ('directory', 'file'):
                    for name, entry in original.items():
                        if reorg.within(name, action['source']):
                            new = action['destination'] + name[len(action['source']):]
                            self.assertEqual(fixture.expected['manifest'][new], entry)
                            self.assertEqual(fixture.expected['mtime_ns'][new], self.baseline['mtime_ns'][name])
                            self.assertEqual(reorg.identity(self.source / new), self.inodes[name])
                            if action['kind'] == 'directory' and entry['kind'] == 'file':
                                moved.append(entry)
            self.assertEqual(fixture.summary['directory_descendant_files'], len(moved))
            self.assertEqual(fixture.summary['directory_descendant_bytes'], sum(entry['size'] for entry in moved))
            self.assertEqual(fixture.summary['existing_file_contents_modified'], 0)
        self.assert_restored()
        self.assertTrue((fixture.backup / 'plan.json').exists())
        self.assertEqual(fixture.record['status'], 'restored')
        fixture.restore()  # Namespace-based recovery is idempotent.
        again = self.prepare()
        self.assertEqual(again.expected, fixture.expected)
        again.restore()

    def test_partial_apply_recovers_from_retained_journal(self):
        fixture = self.prepare()
        move = reorg.ReorgFixture.move
        count = 0

        def interrupt(source, destination):
            nonlocal count
            count += 1
            if count == 13:
                raise KeyboardInterrupt('synthetic interruption during directory reshuffle')
            move(source, destination)

        with patch.object(reorg.ReorgFixture, 'move', staticmethod(interrupt)):
            with self.assertRaises(KeyboardInterrupt):
                fixture.apply()
        reorg.ReorgFixture.open(fixture.backup).restore()
        self.assert_restored()

    def test_context_restores_when_apply_is_interrupted(self):
        fixture = self.prepare()
        move = reorg.ReorgFixture.move
        count = 0

        def interrupt(source, destination):
            nonlocal count
            count += 1
            if count == 90:
                raise KeyboardInterrupt('synthetic interruption after file renames and some deletions')
            move(source, destination)

        with patch.object(reorg.ReorgFixture, 'move', staticmethod(interrupt)):
            with self.assertRaises(KeyboardInterrupt):
                with fixture.applied():
                    self.fail('apply should have been interrupted')
        self.assert_restored()

    def test_changed_descendant_is_not_overwritten(self):
        fixture = self.prepare()
        directory = fixture.record['actions'][0]
        name = next(name for name, item in self.baseline['manifest'].items()
                    if item['kind'] == 'file' and reorg.within(name, directory['source']))
        original = (self.source / name).read_bytes()
        fixture.apply()
        moved = self.source / (directory['destination'] + name[len(directory['source']):])
        moved.write_bytes(b'external modification\n')
        with self.assertRaisesRegex(ValueError, 'moved-descendant change'):
            fixture.restore()
        self.assertEqual(moved.read_bytes(), b'external modification\n')
        # Undo only this test's deliberate external edit, then recover normally.
        moved.write_bytes(original)
        os.utime(moved, ns=(self.baseline['mtime_ns'][name],) * 2)
        fixture.restore()
        self.assert_restored()

    def test_partial_restore_can_be_reopened_and_finished(self):
        fixture = self.prepare()
        fixture.apply()
        move = reorg.ReorgFixture.move
        count = 0

        def interrupt(source, destination):
            nonlocal count
            count += 1
            if count == 39:
                raise KeyboardInterrupt('synthetic interruption after additions and some deletions restored')
            move(source, destination)

        with patch.object(reorg.ReorgFixture, 'move', staticmethod(interrupt)):
            with self.assertRaises(KeyboardInterrupt):
                fixture.restore()
        reorg.ReorgFixture.open(fixture.backup).restore()
        self.assert_restored()


if __name__ == '__main__':
    unittest.main()
