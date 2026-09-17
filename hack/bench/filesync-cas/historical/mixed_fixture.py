#!/usr/bin/env python3
"""Explicit, reversible 128-edit/64-delete/64-add filesync fixture.

Importing this module never changes source. prepare() stages an owned backup;
only apply()/restore() rename source files. Backups and staged artifacts are
retained, never recursively removed. Original bytes/inodes/modes/mtimes return
on restore; edited files receive deterministic novel mtimes while all other
existing file/directory mtimes remain unchanged. ctimes cannot be restored.
"""
from collections import defaultdict, deque
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from source_manifest import manifest

ROOT = Path(__file__).resolve().parent
PROBE = 'crates/ruff/src/lib.rs'
EXCLUDED = {'.git', 'target', 'dagger.toml', 'dagger.lock'}
COUNTS = {'modify': 128, 'delete': 64, 'add': 64}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def identity(path):
    info = Path(path).lstat()
    return [info.st_dev, info.st_ino]


def snapshot(source):
    source = Path(source)
    entries = manifest(source)
    return {'manifest': entries,
            'mtime_ns': {name: (source / name).lstat().st_mtime_ns for name in entries},
            'root_mtime_ns': source.lstat().st_mtime_ns}


def spaced(values, count):
    need(len(values) >= count, f'need at least {count} eligible values, found {len(values)}')
    return [values[index * len(values) // count] for index in range(count)]


def selection(entries, token):
    """Pure deterministic selection, spread across crates then within each crate."""
    need(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', token) is not None, 'token must be 1..64 lowercase letters/digits/hyphens')
    eligible = []
    for name, item in sorted(entries.items()):
        parts = PurePosixPath(name).parts
        need(parts and not name.startswith('/') and '..' not in parts, 'manifest path is not local')
        if (item['kind'] == 'file' and name != PROBE and not EXCLUDED.intersection(parts)
                and item['size'] <= 1024 * 1024):
            eligible.append(name)
    need(len(eligible) >= 192, 'need 192 eligible regular files of at most 1 MiB')
    groups = defaultdict(list)
    for name in eligible:
        parts = PurePosixPath(name).parts
        group = '/'.join(parts[:2]) if parts[0] == 'crates' and len(parts) > 2 else parts[0]
        groups[group].append(name)
    # Allocate round-robin across top-level/crate groups, then spread each
    # group's allocation evenly over its sorted paths (not just its prefix).
    allocation = dict.fromkeys(groups, 0)
    queue = deque(sorted(groups))
    for _ in range(192):
        group = queue.popleft()
        allocation[group] += 1
        if allocation[group] < len(groups[group]):
            queue.append(group)
    picked = {group: deque(spaced(groups[group], count)) for group, count in allocation.items() if count}
    chosen = []
    while picked:
        for group in sorted(tuple(picked)):
            chosen.append(picked[group].popleft())
            if not picked[group]:
                del picked[group]
    deleted = chosen[2::3]
    modified = [name for index, name in enumerate(chosen) if index % 3 != 2]
    parents = spaced(sorted({str(PurePosixPath(name).parent) for name in eligible}), 64)
    added = [str(PurePosixPath(parent) / f'filesync-mixed-{token}-{index:03d}.txt')
             for index, parent in enumerate(parents)]
    need(not set(added).intersection(entries), 'addition name already exists')
    result = {'modify': modified, 'delete': deleted, 'add': added}
    need({kind: len(names) for kind, names in result.items()} == COUNTS, 'incorrect mixed fixture cardinality')
    return result


def file_entry(data, mode):
    return {'kind': 'file', 'mode': mode, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def write_new(path, value):
    with Path(path).open('x') as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write('\n')


class MixedFixture:
    """Use prepare(...); try: apply(); ... finally: restore(). No engine calls."""

    def __init__(self, backup, record):
        self.backup = Path(backup)
        self.record = record
        self.source = Path(record['source'])

    @classmethod
    def prepare(cls, source, owned_backup_parent, token):
        source = Path(source).absolute()
        parent = Path(owned_backup_parent).absolute()
        need(source.resolve() == source and source.is_dir() and source != ROOT
             and source.is_relative_to(ROOT), 'source must be a real experiment-owned directory')
        need(parent.resolve() == parent and parent.is_dir() and parent.is_relative_to(ROOT)
             and not parent.is_relative_to(source), 'backup parent must be owned and outside source')
        need(source.stat().st_dev == parent.stat().st_dev, 'backup must share source filesystem for atomic renames')
        baseline = snapshot(source)
        paths = selection(baseline['manifest'], token)
        expected = copy.deepcopy(baseline)
        delta = 1_000_000_000 + int(hashlib.sha256(token.encode()).hexdigest()[:8], 16)
        addition_time = max(baseline['mtime_ns'].values()) + delta
        actions, parents = [], {}
        for kind, names in paths.items():
            for name in names:
                path = source / name
                need(path.parent.resolve() == path.parent, 'source ancestry includes a symlink')
                rel_parent = str(PurePosixPath(name).parent)
                parents[rel_parent] = {'identity': identity(path.parent), 'atime_ns': path.parent.stat().st_atime_ns,
                                       'mtime_ns': path.parent.stat().st_mtime_ns}
                action = {'kind': kind, 'path': name, 'index': len(actions)}
                if kind != 'add':
                    info = path.lstat()
                    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_dev == source.stat().st_dev,
                         'selected source must be a regular, non-hardlinked file on the source filesystem')
                    action['original'] = {'identity': identity(path), 'uid': info.st_uid, 'gid': info.st_gid,
                                          'atime_ns': info.st_atime_ns, 'mtime_ns': info.st_mtime_ns}
                else:
                    need(not os.path.lexists(path), 'addition path appeared')
                actions.append(action)
        backup = Path(tempfile.mkdtemp(prefix='mixed-fixture-', dir=parent))
        (backup / 'slots').mkdir()
        record = {'version': 1, 'status': 'preparing', 'source': str(source), 'source_identity': identity(source),
                  'backup': str(backup), 'backup_identity': identity(backup), 'token': token, 'counts': COUNTS,
                  'slots_identity': identity(backup / 'slots'),
                  'baseline': baseline, 'expected': expected, 'parents': parents, 'actions': actions}
        obj = cls(backup, record)
        try:
            for action in actions:
                kind, name = action['kind'], action['path']
                if kind == 'delete':
                    del expected['manifest'][name]
                    del expected['mtime_ns'][name]
                    continue
                if kind == 'modify':
                    data = (source / name).read_bytes() + f'\n// filesync-mixed {token} {action["index"]}\n'.encode()
                    mode = baseline['manifest'][name]['mode']
                    mtime = baseline['mtime_ns'][name] + delta
                else:
                    data = f'filesync-mixed addition {token} {action["index"]}\n'.encode()
                    mode, mtime = 0o644, addition_time
                staged = obj.slot(action, 'new')
                with staged.open('xb') as output:
                    output.write(data)
                if kind == 'modify':
                    os.chown(staged, action['original']['uid'], action['original']['gid'])
                staged.chmod(mode)
                os.utime(staged, ns=(mtime, mtime))
                action['replacement_identity'] = identity(staged)
                expected['manifest'][name] = file_entry(data, mode)
                expected['mtime_ns'][name] = mtime
            need(snapshot(source) == baseline, 'source changed while staging; no source mutations were made')
            record['status'] = 'prepared'
        except BaseException as error:
            record.update(status='preparation-failed', error=repr(error))
            raise
        finally:
            write_new(backup / 'plan.json', record)
        return obj

    @classmethod
    def open(cls, backup):
        backup = Path(backup).absolute()
        need(backup.is_relative_to(ROOT) and backup.resolve() == backup and backup.name.startswith('mixed-fixture-'),
             'backup must be an owned real mixed-fixture directory')
        record = json.loads((backup / 'plan.json').read_text())
        need(record['version'] == 1 and record['backup'] == str(backup), 'unexpected fixture record')
        obj = cls(backup, record)
        obj.guard()
        return obj

    @property
    def expected(self):
        return self.record['expected']

    @property
    def baseline(self):
        return self.record['baseline']

    def slot(self, action, suffix):
        return self.backup / 'slots' / f'{action["index"]:03d}.{suffix}'

    def save(self, status):
        self.record['status'] = status
        # Only this helper's retained journal is updated; source receipts and
        # all unrelated raw evidence remain untouched.
        (self.backup / 'plan.json').write_text(json.dumps(self.record, indent=2, sort_keys=True) + '\n')

    def guard(self):
        need(self.source.is_relative_to(ROOT) and self.source != ROOT and self.source.resolve() == self.source,
             'source path escaped or ancestry changed')
        need(identity(self.source) == self.record['source_identity'], 'source root replaced')
        need(identity(self.backup) == self.record['backup_identity'] and self.backup.resolve() == self.backup,
             'backup directory replaced')
        slots = self.backup / 'slots'
        need(slots.resolve() == slots and identity(slots) == self.record['slots_identity'], 'backup slots replaced')
        need(not self.backup.is_relative_to(self.source), 'backup moved inside source')
        for name, info in self.record['parents'].items():
            path = self.source / name
            need(path.resolve() == path and identity(path) == info['identity'], 'affected parent replaced')

    def normalize_parent_times(self):
        for name, info in self.record['parents'].items():
            os.utime(self.source / name, ns=(info['atime_ns'], info['mtime_ns']))

    @staticmethod
    def move(source, destination):
        need(not os.path.lexists(destination), f'refuse existing rename destination: {destination}')
        os.rename(source, destination)

    def apply(self):
        self.guard()
        need(self.record['status'] == 'prepared', 'fixture is not unused/prepared')
        need(snapshot(self.source) == self.baseline, 'source changed before mixed diff')
        self.verify_restorable()
        self.save('applying')
        for action in self.record['actions']:
            path = self.source / action['path']
            if action['kind'] != 'add':
                need(identity(path) == action['original']['identity'], 'original inode changed')
                self.move(path, self.slot(action, 'original'))
            if action['kind'] != 'delete':
                need(identity(self.slot(action, 'new')) == action['replacement_identity'], 'staged inode changed')
                self.move(self.slot(action, 'new'), path)
        self.normalize_parent_times()
        self.verify_applied()
        self.save('applied')

    def verify_applied(self):
        self.guard()
        need(snapshot(self.source) == self.expected, 'mixed diff differs from the exact planned bytes/types/modes/mtimes')

    def verify_restorable(self):
        """Validate all source changes and owned inode locations before rollback."""
        self.guard()
        observed = snapshot(self.source)
        allowed = copy.deepcopy(self.baseline)
        for action in self.record['actions']:
            name, kind = action['path'], action['kind']
            path = self.source / name
            present = os.path.lexists(path)
            current_id = identity(path) if present else None
            if kind != 'add':
                original_id = action['original']['identity']
                original_slot = self.slot(action, 'original')
                original_in_source = current_id == original_id
                original_in_backup = os.path.lexists(original_slot)
                if original_in_backup:
                    need(identity(original_slot) == original_id, 'original backup inode replaced')
                need(original_in_source != original_in_backup, 'original inode missing or duplicated')
                info = (path if original_in_source else original_slot).lstat()
                need(info.st_nlink == 1 and info.st_uid == action['original']['uid']
                     and info.st_gid == action['original']['gid'], 'original ownership/link count changed')
                if original_in_backup:
                    need(file_entry(original_slot.read_bytes(), stat.S_IMODE(info.st_mode)) == self.baseline['manifest'][name]
                         and info.st_mtime_ns == self.baseline['mtime_ns'][name], 'original backup changed')
            if kind != 'delete':
                replacement_id = action['replacement_identity']
                locations = [path, self.slot(action, 'new'), self.slot(action, 'used')]
                need(sum(os.path.lexists(value) and identity(value) == replacement_id for value in locations) == 1,
                     'replacement inode missing or duplicated')
                for location in locations[1:]:
                    if os.path.lexists(location):
                        need(identity(location) == replacement_id, 'replacement backup inode replaced')
                        info = location.lstat()
                        need(file_entry(location.read_bytes(), stat.S_IMODE(info.st_mode)) == self.expected['manifest'][name]
                             and info.st_mtime_ns == self.expected['mtime_ns'][name], 'staged replacement changed')
            if not present:
                allowed['manifest'].pop(name, None)
                allowed['mtime_ns'].pop(name, None)
            elif kind != 'delete' and current_id == action['replacement_identity']:
                allowed['manifest'][name] = self.expected['manifest'][name]
                allowed['mtime_ns'][name] = self.expected['mtime_ns'][name]
            else:
                need(kind != 'add' and current_id == action['original']['identity'], 'source path replaced externally')
        # Atomic renames legitimately change parent times until normalization;
        # every non-parent mtime and every manifest entry must still match.
        for parent in self.record['parents']:
            if parent == '.':
                allowed['root_mtime_ns'] = observed['root_mtime_ns']
            else:
                allowed['mtime_ns'][parent] = observed['mtime_ns'][parent]
        need(observed == allowed, 'unrelated source change detected; refuse rollback overwrite')

    def restore(self):
        need(self.record['status'] != 'preparation-failed', 'preparation failed without mutating source; retain staged evidence')
        self.verify_restorable()
        self.save('restoring')
        for action in reversed(self.record['actions']):
            path = self.source / action['path']
            if action['kind'] != 'delete' and os.path.lexists(path) and identity(path) == action['replacement_identity']:
                self.move(path, self.slot(action, 'used'))
            original = self.slot(action, 'original')
            if action['kind'] != 'add' and os.path.lexists(original):
                self.move(original, path)
        self.normalize_parent_times()
        need(snapshot(self.source) == self.baseline, 'source restoration did not exactly match baseline')
        self.save('restored')


if __name__ == '__main__':
    raise SystemExit('Import MixedFixture from an explicit runner; this helper never applies a fixture from its command line.')
