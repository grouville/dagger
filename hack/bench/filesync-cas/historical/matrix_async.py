#!/usr/bin/env python3
"""Three-arm async-aware matrix, with two distinct large-diff test cases.

Preparation inspects immutable seed receipts and creates unused runtime/XDG
directories; it never starts an engine. Running is explicitly sequential and
restores the owned Ruff fixture and stops the current owned engine on failure.
No raw evidence, engine volumes, or existing outputs are deleted or overwritten.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time

import build
import profile_import
from mixed_fixture import MixedFixture
from reorg_fixture import ReorgFixture
from run_directory_pairs import DIRECTORY, DirectoryMove, move_state, state

ROOT = build.ROOT
SOURCE = ROOT / 'ruff'
PROBE = 'crates/ruff/src/lib.rs'
REVISION = 'c2cd236b9cc5b2149c74247e179d6567ec74066f'
ARMS = ('main', 'both', 'async')
SEEDS = dict(zip(ARMS, (6, 8, 45)))
HEADS = dict(zip(ARMS, (
    'c4512cf1d1a371ca097d13a311c523638f4c7c0b',
    '31064758056ac175f54941d6293eff1905df894a',
    '79a5f0800755dfb8316dd9575cd745ad2f5075db',
)))
LABELS = ('initial', 'exact', 'leaf1', 'leaf1-exact', 'leaf2', 'ab1-exact', 'revert',
          'ab2-edit', 'ab2-exact', 'ab3-edit', 'ab4-edit', 'ab4-exact', 'ab5-edit')
RELATIONS = {
    'initial': (), 'exact': ('--same-as', 'initial'),
    'leaf1': ('--different-from', 'initial'), 'leaf1-exact': ('--same-as', 'leaf1'),
    'leaf2': ('--different-from', 'leaf1'), 'ab1-exact': ('--same-as', 'leaf2'),
    'revert': ('--same-as', 'leaf1'),
    'ab2-edit': ('--different-from', 'leaf1'), 'ab2-exact': ('--same-as', 'ab2-edit'),
    'ab3-edit': ('--same-as', 'leaf1'),
    'ab4-edit': ('--different-from', 'leaf1'), 'ab4-exact': ('--same-as', 'ab4-edit'),
    'ab5-edit': ('--same-as', 'leaf1'),
}
FLOW_NAMES = {
    'initial': 'Cold import', 'exact': 'Unchanged after cold',
    'leaf1': 'App edit', 'leaf1-exact': 'Unchanged after app edit',
    'leaf2': 'Directory move, app edit retained', 'ab1-exact': 'Unchanged after move',
    'revert': 'Restore directory, app edit retained',
    'ab2-edit': 'Mixed content diff: 128 edits, 64 adds, 64 deletes',
    'ab2-exact': 'Repeat mixed content diff', 'ab3-edit': 'Restore mixed content diff',
    'ab4-edit': 'Broad directory/file reorganization + adds/deletes',
    'ab4-exact': 'Repeat broad reorganization', 'ab5-edit': 'Restore broad reorganization',
}
ARM_LABELS = {
    'main': 'Pinned main 523f3fe3 + diagnostics + reserve-floor fix',
    'xattrs': 'Same main + xattr opt-out',
    'cas': 'Same main + result-first flat CAS',
    'both': 'Same main + xattr opt-out + synchronous result-first CAS',
    'async': 'Same CAS + asynchronous admission (79a5f080)',
}
HELPERS = (
    'matrix_async.py', 'matrix.py', 'summarize_async_matrix.py', 'async_samples.py', 'build.py', 'profile_import.py',
    'profile_async.py', 'profile_windows.py', 'mixed_fixture.py', 'reorg_fixture.py', 'verify_fixture_export.py',
    'profile_phase.py', 'source_manifest.py', 'run_directory_pairs.py',
    'verify_filesync_export.py', 'stop_filesync_runtime.py',
    'summarize_filesync_pairs.py', 'import.graphql', 'import_export.graphql',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def save_record(path, value):
    # Only the record created by this invocation is updated, never raw samples.
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def cohort_path(number):
    require(1 <= number <= 99, 'cohort must be 1..99')
    return ROOT / f'filesync-async-matrix-r{number}'


def runtime_path(attempt):
    require(1 <= attempt <= 128, 'runtime attempt must be 1..128')
    return ROOT / f'runtime-r{attempt}'


def engine_name(attempt):
    return f'dagger-storage-host-efb1uyhh-r{attempt}-engine'


def round_order(number):
    offset = (number - 1) % len(ARMS)
    return list(ARMS[offset:] + ARMS[:offset])


def position_counts(rounds):
    return {arm: {str(position + 1): sum(row['order'][position] == arm for row in rounds)
                  for position in range(len(ARMS))} for arm in ARMS}


def helper_hashes():
    return {name: build.sha(ROOT / name) for name in HELPERS}


def clean_source():
    env = build.environment()
    require(build.read(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], env) == REVISION, 'Ruff revision differs')
    require(build.read(['git', '-C', str(SOURCE), 'status', '--porcelain'], env) == '', 'owned Ruff source is not clean')


def require_absent_engine(attempt):
    for kind in ('container', 'volume'):
        proc = subprocess.run(['docker', kind, 'inspect', engine_name(attempt)],
                              env=build.environment(), capture_output=True, text=True, timeout=30)
        require(proc.returncode != 0 and 'no such' in proc.stderr.lower(), f'{kind} already exists or inspect failed: {attempt}')


def pinned_source(receipt, filename, optional=False):
    source = Path(receipt['source_directory']).resolve()
    require(source.is_relative_to(ROOT) and (source / '.git').is_dir(), 'seed source is not an owned checkout')
    pins = receipt['source_pins']
    require(pins['files'] == {}, 'matrix seeds must have committed, clean source pins')
    proc = subprocess.run(['git', '-C', str(source), 'show', f"{pins['head']}:{filename}"],
                          env=build.environment(), capture_output=True, timeout=30)
    if optional and proc.returncode != 0 and b'does not exist' in proc.stderr:
        return b''
    require(proc.returncode == 0, f'cannot read pinned seed source {filename}: {proc.stderr.decode(errors="replace")}')
    return proc.stdout


def inspect_seed(arm, number):
    runtime = runtime_path(number)
    image_path = runtime / 'image.json'
    image = read_json(image_path)
    receipt_path = Path(image['build_receipt']).resolve()
    require(receipt_path.is_relative_to(ROOT), 'matrix requires experiment-owned build receipts')
    receipt = read_json(receipt_path)
    reviewed_r12 = (receipt_path == ROOT / 'build-r12/receipt.json'
                    and build.sha(receipt_path) == 'ec06bc4156d8b4f35bd271c0e611c9cb8e48e1820cbe8d5de37e47b5f6c23fbc')
    require(receipt['status'] == 'exported' and receipt['exit_code'] == 0 and (build.inventory_compatible(receipt) or reviewed_r12),
            'seed build incomplete, failed, or inventory changed')
    require(receipt['source_pins'] == image['source_pins'], 'seed source pins differ')
    require(receipt['archive_sha256'] == image['archive_sha256'], 'seed archive identity differs')
    require(build.sha(runtime / 'dagger') == image['cli_sha256'], 'seed CLI bytes changed')
    actual = build.read(['docker', 'image', 'inspect', image['tag'], '--format', '{{.Id}}'], build.environment())
    require(actual == image['id'], 'seed image tag changed')
    client = pinned_source(receipt, 'engine/client/filesync.go')
    local = pinned_source(receipt, 'engine/filesync/localfs.go')
    cache = pinned_source(receipt, 'engine/filesync/filecache.go', optional=True)
    xattrs = arm in ('xattrs', 'both', 'async')
    cas = arm in ('cas', 'both', 'async')
    require((b'fsutil.WithSkipXattrs()' in client) == xattrs
            and (b'fsutil.WithSkipXattrs()' in local) == xattrs, 'seed xattr arm does not match both client/engine source')
    require((b'copier.CopyToEmpty(' in local and b'fileCache.publish(ctx)' in local
             and b'func (c *fileCacheCopy) materialize(' in cache) == cas,
            'seed result-first arm does not match source')
    if not cas:
        require(not cache, 'non-CAS arm unexpectedly contains the inode cache')
    require(image['source_pins']['head'] == HEADS[arm], f'{arm} source differs from the reviewed frozen commit')
    gc = pinned_source(receipt, 'dagql/cache_prune.go')
    require(b'target = min(target, max(0, usedBytes-policy.ReservedSpace))' in gc, 'seed lacks the common reserve-floor clamp')
    return {
        'runtime': number, 'image': image, 'source_role': receipt['source_role'],
        'build_receipt_sha256': build.sha(receipt_path), 'seed_image_sha256': build.sha(image_path),
        'gc_source_sha256': hashlib.sha256(gc).hexdigest(),
        'gc_tests_sha256': hashlib.sha256(pinned_source(receipt, 'dagql/cache_test.go')).hexdigest(),
        'send_source_sha256': hashlib.sha256(pinned_source(receipt, 'internal/fsutil/send.go')).hexdigest(),
        'send_profile_sha256': hashlib.sha256(pinned_source(receipt, 'internal/fsutil/send_profile.go')).hexdigest(),
    }


def prepare(args):
    clean_source()
    output = cohort_path(args.cohort)
    require(not output.exists(), 'refuse an existing matrix directory')
    require(args.first_attempt >= 2 and args.first_attempt + 6 * len(ARMS) - 1 <= 128, 'fresh attempts must fit in 2..128')
    seeds = {arm: inspect_seed(arm, SEEDS[arm]) for arm in ARMS}
    for key in ('gc_source_sha256', 'gc_tests_sha256', 'send_source_sha256', 'send_profile_sha256'):
        require(len({seed[key] for seed in seeds.values()}) == 1, f'arms differ in common {key}')
    rounds = []
    for number in range(1, 7):
        arms = {}
        for offset, arm in enumerate(ARMS):
            attempt = args.first_attempt + (number - 1) * len(ARMS) + offset
            require(not runtime_path(attempt).exists(), f'refuse existing runtime-r{attempt}')
            require_absent_engine(attempt)
            image = seeds[arm]['image']
            arms[arm] = {'attempt': attempt, 'seed_runtime': SEEDS[arm], 'image': image['id'],
                         'cli_sha256': image['cli_sha256'], 'source_pins': image['source_pins']}
        rounds.append({'round': number, 'order': round_order(number), 'arms': arms})
    plan = {
        'status': 'preparing', 'cohort': args.cohort, 'rounds': rounds, 'seeds': seeds,
        'arm_labels': ARM_LABELS, 'labels': list(LABELS), 'source_revision': REVISION,
        'helpers': helper_hashes(), 'nonce': secrets.token_hex(6),
        'scope': 'Three matched filesync arms; original flows plus separate mixed-content and broad-reorganization cases; no Cargo/module or unprofiled claim.',
        'cold': 'New engine volume and CLI XDG state per arm; images and host OS page caches already available.',
        'gc': 'Default configuration; the identical existing reserve-floor fix is present in all three arms. All GC tails retained.',
        'config': {'logLevel': 'debug'}, 'position_counts': position_counts(rounds),
        'order_caveat': 'Six cyclic rounds over three arms: every arm occupies every position twice.',
        'sequence_caveat': 'The directory move retains the app edit; revert restores the directory only and must match leaf1. This is not the old separate directory-cohort sequence.',
        'readback_scope': 'First round, all three arms, edited/moved/mixed/reorganized trees; validation-separated imports, not retained snapshot-ID readback or immediate-overlap stress.',
        'async_capture': 'Foreground stays CLI-bounded; only explicit independent admission roots may extend up to 10s beyond CLI; all events retained.',
    }
    output.mkdir()
    plan_path = output / 'receipt.json'
    write_new(plan_path, plan)
    try:
        for row in rounds:
            for arm, spec in row['arms'].items():
                runtime = runtime_path(spec['attempt'])
                runtime.mkdir()
                shutil.copy2(runtime_path(SEEDS[arm]) / 'dagger', runtime / 'dagger')
                require(build.sha(runtime / 'dagger') == spec['cli_sha256'], 'copied CLI identity changed')
                write_new(runtime / 'image.json', seeds[arm]['image'])
                config = runtime / 'cli/config/dagger/engine.json'
                config.parent.mkdir(parents=True)
                write_new(config, {'logLevel': 'debug'})
        plan['status'] = 'prepared-not-measured'
    except BaseException as error:
        plan.update(status='preparation-failed', error=repr(error))
        raise
    finally:
        save_record(plan_path, plan)
    print(json.dumps({'matrix': str(output), 'status': plan['status'], 'position_counts': plan['position_counts']}))


def round_fixture(plan, row, baseline, original):
    number = row['round']
    suffix = f'\n// filesync-matrix-{plan["nonce"]}-c{plan["cohort"]}-round-{number}\n'.encode()
    edited = original + suffix
    edit_state = copy.deepcopy(baseline)
    edit_state['manifest'][PROBE].update(size=len(edited), sha256=hashlib.sha256(edited).hexdigest())
    edit_state['mtime_ns'][PROBE] += number * 1_000_000_000
    parent = str(Path(DIRECTORY).parent / f'matrix-{plan["nonce"]}-c{plan["cohort"]}-r{number}')
    move_mtime = baseline['mtime_ns'][str(Path(DIRECTORY).parent)] + number * 1_000_000_000
    moved = move_state(edit_state, DIRECTORY, parent, move_mtime)
    expected = {label: baseline if label in ('initial', 'exact') else
                moved if label in ('leaf2', 'ab1-exact') else edit_state for label in LABELS}
    return edited, edit_state, moved, parent, move_mtime, expected


def command(script, *args):
    argv = [sys.executable, str(ROOT / script), *map(str, args)]
    print('RUN', *argv, flush=True)
    subprocess.run(argv, check=True, timeout=420)


def inspect_owned(attempt, image, previous):
    require(build.sha(profile_import.GUARD) == profile_import.PINS[profile_import.GUARD], 'ownership helper changed')
    module = importlib.util.spec_from_file_location('matrix_ownership', profile_import.GUARD)
    guard = importlib.util.module_from_spec(module)
    module.loader.exec_module(guard)

    def selected(kind, fields):
        template = '{' + ','.join(json.dumps(key) + ':{{json .' + key + '}}' for key in fields) + '}'
        return json.loads(build.read(['docker', kind, 'inspect', engine_name(attempt), '--format', template], build.environment()))

    row = selected('container', ('Id', 'Name', 'Image', 'Mounts', 'State.Running', 'State.Pid', 'State.StartedAt', 'RestartCount'))
    owned = guard.engine(row, engine_name(attempt), image['id'], runtime_path(attempt) / 'cli/config/dagger/engine.json',
                         previous['engine'] if previous and row['State.Running'] else None)
    if previous and not row['State.Running']:
        # A stopped container has PID zero; all other immutable identity fields
        # must still match before its logs are accepted. Never restart it.
        require(all(owned[key] == value for key, value in previous['engine'].items() if key != 'pid'), 'stopped owner changed')
    volume = guard.volume(selected('volume', ('Name', 'Driver', 'Mountpoint', 'CreatedAt', 'Scope', 'Options', 'Labels')),
                          owned, previous['volume'] if previous else None)
    return row, {'engine': owned, 'volume': volume}


def stop_runtime(attempt):
    """Also recover validated ownership if the first capture failed before saving it."""
    runtime = runtime_path(attempt)
    proc = subprocess.run(['docker', 'container', 'inspect', engine_name(attempt)],
                          env=build.environment(), capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        require('no such' in proc.stderr.lower(), 'cannot determine whether the owned engine needs stopping')
        write_new(runtime / 'matrix-stop.json', {'status': 'no-container', 'data_removed': False, 'checked_ns': time.time_ns()})
        return
    owner_path = runtime / 'owner.json'
    previous = read_json(owner_path) if owner_path.exists() else None
    row, owner = inspect_owned(attempt, read_json(runtime / 'image.json'), previous)
    if previous is None:
        write_new(owner_path, owner)
    if row['State.Running']:
        command('stop_filesync_runtime.py', attempt)
    else:
        write_new(runtime / 'matrix-stop.json', {'status': 'already-stopped', 'owner': owner,
                                               'data_removed': False, 'checked_ns': time.time_ns()})
        with (runtime / 'engine-complete.log').open('xb') as stream:
            subprocess.run(['docker', 'logs', owner['engine']['id']], env=build.environment(),
                           stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=30)


def run(args):
    output = cohort_path(args.cohort)
    plan = read_json(output / 'receipt.json')
    require(plan['status'] == 'prepared-not-measured', 'matrix was not prepared successfully')
    require(plan['helpers'] == helper_hashes(), 'controller/query source changed after preparation')
    require([row['round'] for row in plan['rounds']] == list(range(1, 7)), 'expected six rounds')
    require({arm: inspect_seed(arm, SEEDS[arm]) for arm in ARMS} == plan['seeds'],
            'seed build receipts, image tags, source, or CLI changed after preparation')
    clean_source()
    baseline = state()
    probe = SOURCE / PROBE
    original = probe.read_bytes()
    stamp = probe.stat()
    require(baseline['manifest'][PROBE]['sha256'] == hashlib.sha256(original).hexdigest(), 'probe/baseline mismatch')
    require(len(baseline['manifest']) == 12025, 'unexpected Ruff entry count')
    for row in plan['rounds']:
        require(row['order'] == round_order(row['round']), 'round order changed')
        for arm, spec in row['arms'].items():
            runtime = runtime_path(spec['attempt'])
            require(set(path.name for path in runtime.iterdir()) == {'dagger', 'image.json', 'cli'}, 'runtime has already been used')
            require({str(path.relative_to(runtime / 'cli')) for path in (runtime / 'cli').rglob('*')}
                    == {'config', 'config/dagger', 'config/dagger/engine.json'}, 'CLI XDG state has already been used')
            require(read_json(runtime / 'image.json') == plan['seeds'][arm]['image'], 'runtime image provenance changed')
            require(build.sha(runtime / 'dagger') == spec['cli_sha256'], 'runtime CLI changed')
            require(read_json(runtime / 'cli/config/dagger/engine.json') == {'logLevel': 'debug'}, 'GC config changed')
            require_absent_engine(spec['attempt'])
    write_new(output / 'baseline.json', baseline)
    with (output / 'baseline-probe.bin').open('xb') as stream:
        stream.write(original)
    record = {'status': 'running', 'started_ns': time.time_ns(), 'arms': [],
              'helpers': plan['helpers'], 'plan_sha256': build.sha(output / 'receipt.json'),
              'baseline_sha256': build.sha(output / 'baseline.json'), 'source_restored': False}
    record_path = output / 'run.json'
    write_new(record_path, record)

    def replace_probe(expected, content, mtime_ns):
        require((probe.stat().st_dev, probe.stat().st_ino) == (stamp.st_dev, stamp.st_ino), 'probe inode replaced')
        require(probe.read_bytes() == expected, 'refuse to overwrite an externally edited probe')
        probe.write_bytes(content)
        os.utime(probe, ns=(stamp.st_atime_ns, mtime_ns))

    def terminated(signum, _frame):
        raise SystemExit(f'matrix interrupted by signal {signum}; restoring source and stopping owned engine')

    old_term = signal.signal(signal.SIGTERM, terminated)
    try:
        for row in plan['rounds']:
            number = row['round']
            edited, edit_state, moved, parent, move_mtime, expected = round_fixture(plan, row, baseline, original)
            seen = {}
            seen_exports = {}
            for position, arm in enumerate(row['order'], 1):
                require(state() == baseline, 'source differs before next arm')
                clean_source()
                attempt = row['arms'][arm]['attempt']
                runtime = runtime_path(attempt)
                arm_record = {'round': number, 'arm': arm, 'position': position, 'attempt': attempt,
                              'status': 'running', 'flows': [], 'started_ns': time.time_ns()}
                record['arms'].append(arm_record)
                save_record(record_path, record)
                active_move = None
                active_mixed = None
                active_reorg = None
                failure = None
                try:
                    for label in LABELS:
                        if label == 'leaf1':
                            require(state() == baseline, 'source differs before edit')
                            replace_probe(original, edited, edit_state['mtime_ns'][PROBE])
                        elif label == 'leaf2':
                            active_move = DirectoryMove(edit_state, parent, move_mtime)
                            active_move.move()
                        elif label == 'revert':
                            active_move.restore()
                        if label in ('ab2-edit', 'ab4-edit'):
                            kind = 'mixed' if label == 'ab2-edit' else 'reorg'
                            cls = MixedFixture if kind == 'mixed' else ReorgFixture
                            fixture = cls.prepare(SOURCE, ROOT, f'async-{plan["nonce"]}-r{number}-{kind}')
                            write_new(runtime / f'{kind}-fixture.json', {'backup': str(fixture.backup), 'round': number, 'arm': arm})
                            if kind == 'mixed':
                                active_mixed = fixture
                            else:
                                active_reorg = fixture
                            fixture.apply()
                            expected[label] = {key: fixture.expected[key] for key in ('manifest', 'mtime_ns')}
                            expected['ab2-exact' if kind == 'mixed' else 'ab4-exact'] = expected[label]
                        elif label == 'ab3-edit':
                            active_mixed.restore()
                        elif label == 'ab5-edit':
                            active_reorg.restore()
                        require(state() == expected[label], f'source/mtimes differ before {label}')
                        parity = ['--parity-with', f'runtime-r{seen[label]}/{label}/receipt.json'] if label in seen else []
                        command('profile_async.py', label, '--attempt', attempt, *RELATIONS[label], *parity)
                        observed = state()
                        require(observed == expected[label], f'source/mtimes differ after {label}')
                        require(read_json(runtime / label / 'source-manifest.json') == observed['manifest'], 'capture source differs')
                        write_new(runtime / label / 'matrix-state.json', {
                            'status': 'verified', 'round': number, 'arm': arm, 'label': label,
                            'mtime_ns': observed['mtime_ns'], 'baseline_sha256': record['baseline_sha256'],
                            'run_sha256': plan['helpers']['matrix_async.py'], 'moved': label in ('leaf2', 'ab1-exact'),
                        })
                        seen[label] = attempt
                        arm_record['flows'].append(label)
                        save_record(record_path, record)
                        if number == 1 and label in ('leaf1-exact', 'ab1-exact', 'ab2-exact', 'ab4-exact'):
                            capture = {'leaf1-exact': 'edited', 'ab1-exact': 'moved', 'ab2-exact': 'mixed', 'ab4-exact': 'reorg'}[label]
                            compare = ['--compare-attempt', seen_exports[capture]] if capture in seen_exports else []
                            command('verify_fixture_export.py', attempt, capture, *compare)
                            require(state() == expected[label], 'readback changed source')
                            seen_exports[capture] = attempt
                    arm_record['status'] = 'complete'
                except BaseException as error:
                    failure = error
                    arm_record.update(status='failed', error=repr(error))
                finally:
                    cleanup = []
                    try:
                        if active_reorg is not None:
                            active_reorg.restore()
                        if active_mixed is not None:
                            active_mixed.restore()
                        if active_move is not None:
                            active_move.restore()
                        observed = state()
                        for field in ('manifest', 'mtime_ns'):
                            require({name: value for name, value in observed[field].items() if name != PROBE}
                                    == {name: value for name, value in baseline[field].items() if name != PROBE},
                                    f'non-probe source {field} changed before restoration')
                        require(observed['manifest'][PROBE]['mode'] == baseline['manifest'][PROBE]['mode'],
                                'probe mode changed before restoration')
                        current = probe.read_bytes()
                        require(current in (original, edited), 'probe changed outside the owned edit; refuse overwrite')
                        # Also recover an interruption after the byte write but
                        # before utime, without overwriting unrelated changes.
                        if current != original or observed['mtime_ns'][PROBE] != stamp.st_mtime_ns:
                            replace_probe(current, original, stamp.st_mtime_ns)
                        require(state() == baseline, 'restoration changed source/mtimes')
                        clean_source()
                        arm_record['source_restored'] = True
                    except BaseException as error:
                        cleanup.append({'restore': repr(error)})
                    try:
                        stop_runtime(attempt)
                    except BaseException as error:
                        cleanup.append({'stop': repr(error)})
                    if cleanup:
                        arm_record.update(status='failed', cleanup_errors=cleanup)
                    arm_record['ended_ns'] = time.time_ns()
                    save_record(record_path, record)
                if failure is not None:
                    raise failure
                require(not arm_record.get('cleanup_errors'), f'arm cleanup failed: {arm_record.get("cleanup_errors")}')
        record['status'] = 'complete'
    except BaseException as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        signal.signal(signal.SIGTERM, old_term)
        record['ended_ns'] = time.time_ns()
        try:
            record['source_restored'] = state() == baseline
        except BaseException as error:
            record['final_source_check_error'] = repr(error)
        save_record(record_path, record)
    print(json.dumps({'matrix': str(output), 'status': record['status'], 'samples': 6 * len(ARMS) * len(LABELS)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prep = sub.add_parser('prepare', help='Validate three frozen seeds; create unused runtime folders, never engines')
    prep.add_argument('--cohort', type=int, default=1)
    prep.add_argument('--first-attempt', type=int, default=58)
    execute = sub.add_parser('run', help='Run all thirteen flows sequentially; preserve evidence on failure')
    execute.add_argument('--cohort', type=int, default=1)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else run)(args)


if __name__ == '__main__':
    main()
