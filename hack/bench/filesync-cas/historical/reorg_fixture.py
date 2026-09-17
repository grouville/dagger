#!/usr/bin/env python3
"""Separate broad namespace reshuffle; no content edits to existing files.

24 disjoint populated directories (12 local renames, 12 cross-parent moves),
64 independent cross-parent file renames, 32 deletions and 32 additions.
Only explicit apply()/restore() calls mutate source. Use ``with f.applied():``
for finally-based restoration, including interrupted apply. Original inodes,
bytes, modes, symlink targets and mtimes return; ctimes cannot be restored.
Deleted originals remain in an owned backup while applied; staged additions
and the namespace journal are retained afterward. No recursive deletion.
"""
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

from mixed_fixture import ROOT, PROBE, EXCLUDED, file_entry, identity, need, snapshot, spaced, write_new

COUNTS = {'directory': 24, 'file': 64, 'delete': 32, 'add': 32}


def within(name, parent):
    return name == parent or name.startswith(parent + '/')


def group(name):
    parts = PurePosixPath(name).parts
    return '/'.join(parts[:2]) if parts[0] == 'crates' and len(parts) > 2 else parts[0]


def excluded_paths(source):
    """Record protected names without descending into .git, target, etc."""
    result = []
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            if name in EXCLUDED:
                result.append((Path(directory) / name).relative_to(source).as_posix())
        dirs[:] = sorted(name for name in dirs if name not in EXCLUDED)
    return sorted(result)


def distributed(names, count):
    buckets = defaultdict(deque)
    for name in sorted(names):
        buckets[group(name)].append(name)
    result = []
    while len(result) < count and buckets:
        for key in sorted(tuple(buckets)):
            # Alternate the two ends to spread within each crate as well.
            result.append(buckets[key].popleft() if len(result) % 2 == 0 else buckets[key].pop())
            if not buckets[key]:
                del buckets[key]
            if len(result) == count:
                break
    need(len(result) == count, f'need {count} independent files outside moved directories')
    return result


def selection(entries, token, protected=()):
    """Pure plan: same manifest/protected names/token gives identical mappings."""
    need(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', token) is not None, 'unsafe reorganization token')
    for name in entries:
        parts = PurePosixPath(name).parts
        need(parts and not name.startswith('/') and '..' not in parts and name == str(PurePosixPath(name)),
             'manifest path is not canonical/local')
    protected = tuple(protected) + (PROBE,)
    regular = [name for name, item in entries.items() if item['kind'] == 'file' and name != PROBE
               and not EXCLUDED.intersection(PurePosixPath(name).parts)]
    descendants = Counter()
    for name in regular:
        for parent in PurePosixPath(name).parents:
            descendants[str(parent)] += 1
    candidates = [name for name, item in entries.items() if item['kind'] == 'directory'
                  and len(PurePosixPath(name).parts) >= 3 and 2 <= descendants[name] <= 512
                  and not EXCLUDED.intersection(PurePosixPath(name).parts)
                  and not any(within(path, name) for path in protected)]
    chosen, crate_counts, depth_counts, covered = [], Counter(), Counter(), 0
    for _ in range(COUNTS['directory']):
        available = [name for name in candidates if not any(within(name, old) or within(old, name) for old in chosen)
                     and len(regular) - covered - descendants[name] >= 96]
        need(available, 'not enough disjoint populated directories while retaining 96 independent files')
        name = min(available, key=lambda value: (crate_counts[group(value)], depth_counts[len(PurePosixPath(value).parts)],
                                                 len(PurePosixPath(value).parts), value))
        chosen.append(name)
        crate_counts[group(name)] += 1
        depth_counts[len(PurePosixPath(name).parts)] += 1
        covered += descendants[name]
    need(sum(name.startswith('crates/') for name in crate_counts) >= 2 and len(depth_counts) >= 2,
         'case must span multiple crates and directory depths')
    outside = lambda name: not any(within(name, directory) for directory in chosen)
    parents = sorted(name for name, item in entries.items() if item['kind'] == 'directory' and outside(name)
                     and not EXCLUDED.intersection(PurePosixPath(name).parts))
    need(len(parents) >= 32, 'need 32 existing destination directories outside moved subtrees')

    def elsewhere(name, index):
        old_parent = str(PurePosixPath(name).parent)
        options = [parent for parent in parents if parent != old_parent and group(parent) != group(name)]
        if not options:
            options = [parent for parent in parents if parent != old_parent]
        need(options, 'no independent cross-parent destination')
        return options[index % len(options)]

    actions = []
    for index, name in enumerate(chosen):
        parent = str(PurePosixPath(name).parent) if index % 2 == 0 else elsewhere(name, index)
        actions.append({'kind': 'directory', 'source': name,
                        'destination': str(PurePosixPath(parent) / f'reorg-{token}-dir-{index:02d}')})
    files = distributed([name for name in regular if outside(name)], 96)
    for index, name in enumerate(files[:64]):
        actions.append({'kind': 'file', 'source': name,
                        'destination': str(PurePosixPath(elsewhere(name, index)) / f'reorg-{token}-file-{index:02d}{PurePosixPath(name).suffix}')})
    actions.extend({'kind': 'delete', 'source': name, 'destination': None} for name in files[64:])
    actions.extend({'kind': 'add', 'source': None,
                    'destination': str(PurePosixPath(parent) / f'reorg-{token}-added-{index:02d}.txt')}
                   for index, parent in enumerate(spaced(parents, 32)))
    destinations = [action['destination'] for action in actions if action['destination']]
    need(len(set(destinations)) == len(destinations) and not set(destinations).intersection(entries),
         'reorganization destination already exists or overlaps another destination')
    need(dict(Counter(action['kind'] for action in actions)) == COUNTS, 'incorrect reorganization counts')
    return actions


def transform(baseline, actions, applied):
    """Pure expected state for any subset of the independent atomic renames."""
    result = copy.deepcopy(baseline)
    for action, after in zip(actions, applied):
        if not after:
            continue
        src, dst = action['source'], action['destination']
        if action['kind'] == 'add':
            result['manifest'][dst] = action['entry']
            result['mtime_ns'][dst] = action['mtime_ns']
            continue
        names = [name for name in baseline['manifest'] if within(name, src)]
        for name in names:
            for field in ('manifest', 'mtime_ns'):
                value = result[field].pop(name)
                if dst is not None:
                    result[field][dst + name[len(src):]] = value
    return result


class ReorgFixture:
    def __init__(self, backup, record):
        self.backup, self.record = Path(backup), record
        self.source = Path(record['source'])

    @classmethod
    def prepare(cls, source, owned_backup_parent, token):
        source, parent = Path(source).absolute(), Path(owned_backup_parent).absolute()
        need(source != ROOT and source.is_relative_to(ROOT) and source.resolve() == source and source.is_dir(),
             'source must be a real experiment-owned directory')
        need(parent.is_relative_to(ROOT) and parent.resolve() == parent and parent.is_dir()
             and not parent.is_relative_to(source), 'backup parent must be owned and outside source')
        need(source.stat().st_dev == parent.stat().st_dev, 'backup and source must share a filesystem')
        baseline, protected = snapshot(source), excluded_paths(source)
        actions = selection(baseline['manifest'], token, protected)
        parents = {}
        for index, action in enumerate(actions):
            action['index'] = index
            for name in (action['source'], action['destination']):
                if name is None:
                    continue
                path = source / name
                need(path.parent.resolve() == path.parent, 'affected ancestry contains a symlink')
                info = path.parent.stat()
                parents[str(PurePosixPath(name).parent)] = {'identity': identity(path.parent),
                    'atime_ns': info.st_atime_ns, 'mtime_ns': info.st_mtime_ns}
            if action['destination']:
                need(not os.path.lexists(source / action['destination']), 'destination appeared')
            if action['source']:
                path = source / action['source']
                info = path.lstat()
                need(info.st_dev == source.stat().st_dev and (stat.S_ISDIR(info.st_mode)
                     if action['kind'] == 'directory' else stat.S_ISREG(info.st_mode) and info.st_nlink == 1),
                     'original must be a same-filesystem directory or non-hardlinked regular file')
                action.update(identity=identity(path), uid=info.st_uid, gid=info.st_gid)
        backup = Path(tempfile.mkdtemp(prefix='reorg-fixture-', dir=parent))
        (backup / 'slots').mkdir()
        record = {'version': 1, 'status': 'preparing', 'source': str(source), 'source_identity': identity(source),
                  'backup': str(backup), 'backup_identity': identity(backup), 'slots_identity': identity(backup / 'slots'),
                  'token': token, 'baseline': baseline, 'protected': protected, 'parents': parents, 'actions': actions}
        obj = cls(backup, record)
        try:
            addition_time = max(baseline['mtime_ns'].values()) + 1_000_000_000 + int(hashlib.sha256(token.encode()).hexdigest()[:8], 16)
            for action in actions:
                if action['kind'] == 'add':
                    data = f'reorg addition {token} {action["index"]}\n'.encode()
                    path = obj.slot(action)
                    with path.open('xb') as stream:
                        stream.write(data)
                    path.chmod(0o644)
                    os.utime(path, ns=(addition_time, addition_time))
                    info = path.stat()
                    action.update(identity=identity(path), uid=info.st_uid, gid=info.st_gid,
                                  entry=file_entry(data, 0o644), mtime_ns=addition_time)
            moved_dirs = [action['source'] for action in actions if action['kind'] == 'directory']
            descendant_files = [item for name, item in baseline['manifest'].items() if item['kind'] == 'file'
                                and any(within(name, directory) for directory in moved_dirs)]
            record['summary'] = {'counts': COUNTS, 'directory_renames': 12, 'directory_cross_parent_moves': 12,
                'directory_depths': sorted({len(PurePosixPath(name).parts) for name in moved_dirs}),
                'directory_groups': dict(Counter(group(name) for name in moved_dirs)),
                'directory_descendant_files': len(descendant_files),
                'directory_descendant_bytes': sum(item['size'] for item in descendant_files),
                'independent_renamed_file_bytes': sum(baseline['manifest'][action['source']]['size'] for action in actions if action['kind'] == 'file'),
                'deleted_file_bytes': sum(baseline['manifest'][action['source']]['size'] for action in actions if action['kind'] == 'delete'),
                'added_file_bytes': sum(action['entry']['size'] for action in actions if action['kind'] == 'add'),
                'existing_file_contents_modified': 0}
            record['summary']['existing_affected_files'] = len(descendant_files) + COUNTS['file'] + COUNTS['delete']
            record['summary']['existing_affected_bytes'] = sum(record['summary'][key] for key in
                ('directory_descendant_bytes', 'independent_renamed_file_bytes', 'deleted_file_bytes'))
            record['expected'] = transform(baseline, actions, [True] * len(actions))
            need(snapshot(source) == baseline and excluded_paths(source) == protected, 'source changed during staging')
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
        need(backup.is_relative_to(ROOT) and backup.resolve() == backup and backup.name.startswith('reorg-fixture-'), 'unowned backup')
        record = json.loads((backup / 'plan.json').read_text())
        need(record['version'] == 1 and record['backup'] == str(backup), 'unexpected reorganization journal')
        obj = cls(backup, record)
        obj.guard()
        return obj

    baseline = property(lambda self: self.record['baseline'])
    expected = property(lambda self: self.record['expected'])
    summary = property(lambda self: self.record['summary'])

    def slot(self, action):
        return self.backup / 'slots' / f'{action["index"]:03d}.file'

    def endpoints(self, action):
        before = self.source / action['source'] if action['source'] else self.slot(action)
        after = self.source / action['destination'] if action['destination'] else self.slot(action)
        return before, after

    def guard(self):
        for path, expected in ((self.source, self.record['source_identity']), (self.backup, self.record['backup_identity']),
                               (self.backup / 'slots', self.record['slots_identity'])):
            need(path != ROOT and path.is_relative_to(ROOT) and path.resolve() == path and identity(path) == expected,
                 'owned root/slots replaced or escaped')
        need(not self.backup.is_relative_to(self.source), 'backup is inside source')
        for name, info in self.record['parents'].items():
            path = self.source / name
            need(path.resolve() == path and identity(path) == info['identity'], 'affected parent replaced')
        need(excluded_paths(self.source) == self.record['protected'], 'excluded namespace changed')

    def save(self, status):
        self.record['status'] = status
        (self.backup / 'plan.json').write_text(json.dumps(self.record, indent=2, sort_keys=True) + '\n')

    @staticmethod
    def move(source, destination):
        need(not os.path.lexists(destination), f'refuse existing rename destination: {destination}')
        os.rename(source, destination)

    def normalize_parent_times(self):
        for name, info in self.record['parents'].items():
            os.utime(self.source / name, ns=(info['atime_ns'], info['mtime_ns']))

    def positions(self):
        result = []
        for action in self.record['actions']:
            endpoints = self.endpoints(action)
            present = [os.path.lexists(path) for path in endpoints]
            need(sum(present) == 1, 'original/reorganized inode missing, duplicated, or destination externally created')
            after = present[1]
            path = endpoints[int(after)]
            info = path.lstat()
            need(identity(path) == action['identity'] and info.st_uid == action['uid'] and info.st_gid == action['gid'],
                 'owned inode or ownership changed')
            if path.parent == self.backup / 'slots':
                entry = action['entry'] if action['kind'] == 'add' else self.baseline['manifest'][action['source']]
                mtime = action['mtime_ns'] if action['kind'] == 'add' else self.baseline['mtime_ns'][action['source']]
                need(file_entry(path.read_bytes(), stat.S_IMODE(info.st_mode)) == entry and info.st_mtime_ns == mtime,
                     'backup/staged bytes, mode or mtime changed')
            result.append(after)
        return result

    def verify_restorable(self):
        self.guard()
        positions = self.positions()
        expected = transform(self.baseline, self.record['actions'], positions)
        observed = snapshot(self.source)
        for name in self.record['parents']:
            if name == '.':
                expected['root_mtime_ns'] = observed['root_mtime_ns']
            else:
                expected['mtime_ns'][name] = observed['mtime_ns'][name]
        need(observed == expected, 'unrelated source or moved-descendant change; refuse rollback overwrite')
        return positions

    def apply(self):
        need(self.record['status'] == 'prepared', 'fixture is not unused/prepared')
        need(not any(self.verify_restorable()) and snapshot(self.source) == self.baseline, 'source differs before reorganization')
        self.save('applying')
        for action in self.record['actions']:
            self.move(*self.endpoints(action))
        self.normalize_parent_times()
        self.verify_applied()
        self.save('applied')

    def verify_applied(self):
        self.guard()
        need(all(self.positions()) and snapshot(self.source) == self.expected, 'reorganized state differs from exact plan')

    def restore(self):
        need(self.record['status'] != 'preparation-failed', 'failed staging never mutated source')
        positions = self.verify_restorable()
        self.save('restoring')
        for action, after in reversed(list(zip(self.record['actions'], positions))):
            if after:
                before_path, after_path = self.endpoints(action)
                self.move(after_path, before_path)
        self.normalize_parent_times()
        need(snapshot(self.source) == self.baseline, 'source restoration differs from baseline')
        self.save('restored')

    @contextmanager
    def applied(self):
        try:
            self.apply()
            yield self
        finally:
            self.restore()


if __name__ == '__main__':
    raise SystemExit('Import ReorgFixture from an explicit runner; no source mutation is performed by this command.')
