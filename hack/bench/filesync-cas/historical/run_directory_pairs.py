#!/usr/bin/env python3
"""Run isolated filesync pairs for a populated-directory move and restoration.

Prepare the engines' receipts with prepare_filesync_pairs.py first. This runner
never edits file bytes: it renames one owned fixture directory, profiles the
normal imports, and restores the original layout even after a failed command.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import build
from source_manifest import manifest

ROOT = build.ROOT
SOURCE = ROOT / 'ruff'
DIRECTORY = 'crates/ruff_linter/resources/test/fixtures'
LABELS = ('initial', 'exact', 'leaf2', 'leaf1-exact', 'revert')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def state():
    contents = manifest(SOURCE)
    return {'manifest': contents,
            'mtime_ns': {name: (SOURCE / name).lstat().st_mtime_ns for name in contents}}


def move_state(baseline, original, parent, move_mtime_ns):
    destination = parent + '/fixtures'

    def remap(name):
        return destination + name[len(original):] if name == original or name.startswith(original + '/') else name

    contents = {remap(name): value for name, value in baseline['manifest'].items()}
    mtimes = {remap(name): value for name, value in baseline['mtime_ns'].items()}
    contents[parent] = {'kind': 'directory', 'mode': 0o755}
    mtimes[parent] = move_mtime_ns
    mtimes[str(Path(original).parent)] = move_mtime_ns
    return {'manifest': contents, 'mtime_ns': mtimes}


def run(script, *args):
    argv = [sys.executable, str(ROOT / script), *map(str, args)]
    print('RUN', *argv, flush=True)
    subprocess.run(argv, check=True, timeout=420)


class DirectoryMove:
    def __init__(self, baseline, parent, move_mtime_ns):
        self.baseline = baseline
        self.original = SOURCE / DIRECTORY
        self.parent = SOURCE / parent
        self.destination = self.parent / self.original.name
        self.move_mtime_ns = move_mtime_ns
        self.expected_moved = move_state(baseline, DIRECTORY, parent, move_mtime_ns)
        self.original_stat = self.original.lstat()
        self.outer_stat = self.original.parent.lstat()
        self.parent_identity = None
        self.moved = False
        require(self.original.is_dir() and not self.original.is_symlink(), 'fixture is not a real directory')
        require(self.original.resolve() == self.original, 'fixture ancestry contains a symlink')
        require(not os.path.lexists(self.parent), 'refuse an existing destination parent')

    @staticmethod
    def identity(stat):
        return stat.st_dev, stat.st_ino

    def move(self):
        require(not self.moved and self.parent_identity is None, 'move already active')
        require(state() == self.baseline, 'source changed before directory move')
        require(self.identity(self.original.lstat()) == self.identity(self.original_stat), 'fixture directory replaced')
        require(not os.path.lexists(self.parent), 'destination parent appeared')
        self.parent.mkdir(mode=0o755)
        self.parent_identity = self.identity(self.parent.lstat())
        self.parent.chmod(0o755)
        require(not os.path.lexists(self.destination), 'destination appeared')
        os.rename(self.original, self.destination)
        self.moved = True
        # Make the directory metadata identical in both arms. File bytes and
        # mtimes are untouched; only the two rename parents receive this time.
        os.utime(self.parent, ns=(self.move_mtime_ns, self.move_mtime_ns))
        os.utime(self.original.parent, ns=(self.outer_stat.st_atime_ns, self.move_mtime_ns))
        require(state() == self.expected_moved, 'move changed more than the expected namespace')

    def restore(self):
        if self.parent_identity is None:
            return
        require(self.parent.is_dir() and not self.parent.is_symlink(), 'owned destination parent replaced')
        require(self.identity(self.parent.lstat()) == self.parent_identity, 'owned destination parent identity changed')
        # Inspect the namespace rather than trusting the flag: interruption
        # can occur immediately after either rename has completed.
        if os.path.lexists(self.destination):
            require(not os.path.lexists(self.original), 'refuse to overwrite a newly created original path')
            require(self.destination.is_dir() and not self.destination.is_symlink(), 'moved directory replaced')
            require(self.identity(self.destination.lstat()) == self.identity(self.original_stat), 'moved directory identity changed')
            os.rename(self.destination, self.original)
        else:
            require(self.original.is_dir() and not self.original.is_symlink(), 'original and moved directories are both absent')
            require(self.identity(self.original.lstat()) == self.identity(self.original_stat), 'original directory identity changed')
        self.moved = False
        # Deliberately not recursive: unexpected contents are never deleted.
        self.parent.rmdir()
        self.parent_identity = None
        os.utime(self.original.parent, ns=(self.outer_stat.st_atime_ns, self.outer_stat.st_mtime_ns))
        require(state() == self.baseline, 'source bytes, namespace or mtimes changed after restoration')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=int, choices=range(3, 10), default=3)
    args = parser.parse_args()
    cohort = ROOT / f'filesync-pairs-r{args.cohort}'
    plan = read_json(cohort / 'receipt.json')
    require([pair['pair'] for pair in plan['pairs']] == list(range(1, 7)), 'expected six pairs')
    env = build.environment()

    def clean():
        require(build.read(['git', '-C', str(SOURCE), 'status', '--porcelain'], env) == '', 'owned source is not clean')

    clean()
    baseline = state()
    moved_entries = {name: item for name, item in baseline['manifest'].items()
                     if name == DIRECTORY or name.startswith(DIRECTORY + '/')}
    require(moved_entries.get(DIRECTORY, {}).get('kind') == 'directory', 'missing populated fixture directory')
    require(sum(item['kind'] == 'file' for item in moved_entries.values()) > 100, 'fixture is unexpectedly small')
    for pair in plan['pairs']:
        require(pair['order'] == (['main', 'cas'] if pair['pair'] % 2 else ['cas', 'main']), 'nonalternating plan')
        for arm in pair['order']:
            runtime = ROOT / f"runtime-r{pair['arms'][arm]['attempt']}"
            require(not any((runtime / name).exists() for name in (*LABELS, 'owner.json', 'stopped.json', 'export.json')),
                    'refuse an already-used runtime')
    write_new(cohort / 'directory-baseline.json', baseline)
    record = {
        'status': 'running', 'scope': 'Nested populated-directory move; filesync only, no Cargo compilation.',
        'run_sha256': build.sha(__file__), 'summarizer_sha256': build.sha(ROOT / 'summarize_directory_pairs.py'),
        'controller_sha256': build.sha(ROOT / 'profile_import.py'),
        'manifest_helper_sha256': build.sha(ROOT / 'source_manifest.py'),
        'baseline_sha256': build.sha(cohort / 'directory-baseline.json'),
        'plan_sha256': build.sha(cohort / 'receipt.json'), 'source_revision': plan['source_revision'],
        'directory': DIRECTORY, 'labels': list(LABELS), 'moves': [],
        'moved_entries': len(moved_entries),
        'moved_files': sum(item['kind'] == 'file' for item in moved_entries.values()),
        'moved_file_bytes': sum(item['size'] for item in moved_entries.values() if item['kind'] == 'file'),
        'started_ns': time.time_ns(),
    }
    record_path = cohort / 'directory-run.json'
    write_new(record_path, record)

    def save():
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')

    active_move = None
    try:
        for pair in plan['pairs']:
            seen = {}
            number = pair['pair']
            parent = str(Path(DIRECTORY).parent / f'flat-filesync-efb1uyhh-c{args.cohort}-pair-{number}')
            move_mtime_ns = baseline['mtime_ns'][str(Path(DIRECTORY).parent)] + number * 1_000_000_000
            record['moves'].append({'pair': number, 'parent': parent, 'move_mtime_ns': move_mtime_ns})
            save()
            for arm in pair['order']:
                clean()
                active_move = DirectoryMove(baseline, parent, move_mtime_ns)
                attempt = pair['arms'][arm]['attempt']
                runtime = ROOT / f'runtime-r{attempt}'
                try:
                    for label, relation in (
                        ('initial', []), ('exact', ['--same-as', 'initial']),
                        ('leaf2', ['--different-from', 'initial']),
                        ('leaf1-exact', ['--same-as', 'leaf2']), ('revert', ['--same-as', 'initial']),
                    ):
                        if label == 'leaf2':
                            active_move.move()
                        elif label == 'revert':
                            active_move.restore()
                        expected = active_move.expected_moved if active_move.moved else baseline
                        require(state() == expected, f'source differs before {label}')
                        parity = ['--parity-with', f'runtime-r{seen[label]}/{label}/receipt.json'] if label in seen else []
                        run('profile_import.py', label, '--attempt', attempt, *relation, *parity)
                        observed = state()
                        require(observed == expected, f'source differs after {label}')
                        require(read_json(runtime / label / 'source-manifest.json') == expected['manifest'], 'controller source differs')
                        write_new(runtime / label / 'directory-state.json', {
                            'status': 'verified', 'run_sha256': record['run_sha256'], 'label': label,
                            'mtime_ns': observed['mtime_ns'], 'baseline_sha256': record['baseline_sha256'],
                            'moved': active_move.moved, 'parent': parent,
                        })
                        seen[label] = attempt
                    if number == 1:
                        # Verify the full moved tree only after all timed flows.
                        # The existing export helper reimports; this is not a
                        # retained-snapshot-ID or cold-snapshot correctness test.
                        active_move.move()
                        prior = pair['arms'][pair['order'][0]]['attempt']
                        compare = ['--compare-attempt', prior] if arm != pair['order'][0] else []
                        run('verify_filesync_export.py', attempt, *compare)
                        active_move.restore()
                finally:
                    active_move.restore()
                    clean()
                active_move = None
                run('stop_filesync_runtime.py', attempt)
        record['status'] = 'complete'
    except BaseException as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        try:
            if active_move is not None:
                active_move.restore()
            clean()
            require(state() == baseline, 'final source differs from baseline')
            record['source_restored'] = True
        finally:
            record['ended_ns'] = time.time_ns()
            save()
    run('summarize_directory_pairs.py', '--cohort', args.cohort, '--write')


if __name__ == '__main__':
    main()
