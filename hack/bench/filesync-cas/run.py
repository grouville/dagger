#!/usr/bin/env python3
"""Portable, sequential Ruff filesync comparison. See README.md before running.

Reuses the historical fixture and async-window validators, not the original
machine-specific build receipts. Results are a new cohort, never replacements
for the published matrix. Only a newly created copy of Ruff is edited.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'historical'))
import mixed_fixture as mixed
import reorg_fixture as reorg
import run_directory_pairs as directory
import profile_windows as windows
from source_manifest import manifest

REVISION = 'c2cd236b9cc5b2149c74247e179d6567ec74066f'
FLOWS = ('cold', 'unchanged', 'edit', 'repeat-edit', 'move', 'repeat-move',
         'restore-move', 'mixed', 'repeat-mixed', 'restore-mixed',
         'reorganization', 'repeat-reorganization', 'restore-reorganization')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def command(argv, **kwargs):
    return subprocess.run(list(map(str, argv)), check=True, capture_output=True,
                          timeout=kwargs.pop('timeout', 60), **kwargs).stdout


def inspect(name):
    return json.loads(command(['docker', 'inspect', name]))[0]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def union_ms(intervals):
    total, end = 0, 0
    for start, stop in sorted(intervals):
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total / 1e6


def profile(directory, owner, env, record, analyzer):
    windows.capture(directory, owner['Id'], env, record['process_ended_ns'])
    path = directory / 'profile.wcprof'
    header, events = windows.decode(path.read_text())
    need(header['event_count'] == len(events) and not header['dropped_events']
         and not header.get('open_ops'), 'incomplete native profile')
    gates, tail = windows.validate(record, header, events)
    need(all(gates.values()), f'profile window validation failed: {gates}')
    analysis = command([analyzer, path], timeout=120).decode()
    (directory / 'analysis.txt').write_text(analysis)
    drift = re.search(r'drift vs actual:\s*([+-]?[\d.]+)%', analysis)
    need(drift and abs(float(drift[1])) <= 2, 'native replay drift missing or too large')
    classes = {}
    for event in events:
        if event['e'] == 'op':
            classes.setdefault(header['strings'][event['c']], []).append((event['s'], event['d']))
    return {'class_ms': {key: union_ms(value) for key, value in classes.items()},
            'admission': tail, 'gates': gates, 'profile_sha256': digest(path)}


def environment(runtime, image, name):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('DAGGER_', '_DAGGER_', '_EXPERIMENTAL_DAGGER_', 'OTEL_', 'XDG_'))
           and key.upper() not in ('TRACEPARENT', 'TRACESTATE', 'BAGGAGE')}
    for category in ('CONFIG', 'CACHE', 'DATA', 'STATE'):
        env['XDG_' + category + '_HOME'] = str(runtime / 'cli' / category.lower())
    env.update(DO_NOT_TRACK='1', DNT='1', DAGGER_NO_NAG='1', DAGGER_LEAVE_OLD_ENGINE='1',
               _DAGGER_FILESYNC_PHASE_PROFILE='1',
               DAGGER_ENGINE=f'image+docker://{image}?container={name}&volume={name}&cleanup=false')
    return env


def run_arm(args, root, source, arm, image, round_number, nonce, references):
    runtime = root / f'r{round_number}-{arm}'
    runtime.mkdir()
    config = runtime / 'cli/config/dagger/engine.json'
    config.parent.mkdir(parents=True)
    save(config, {'logLevel': 'debug'})
    name = f'dagger-filesync-share-{nonce}-r{round_number}-{arm}'
    image_id = inspect(image)['Id']
    cli = runtime / 'dagger'
    # Extract the CLI from the exact engine image. This never starts a container.
    extractor = command(['docker', 'create', '--entrypoint=/bin/true', image_id]).decode().strip()
    try:
        command(['docker', 'cp', extractor + ':/usr/local/bin/dagger', cli])
    finally:
        command(['docker', 'rm', '-v', extractor])
    env = environment(runtime, image, name)
    save(runtime / 'inputs.json', {'image': image, 'image_id': image_id, 'cli_sha256': digest(cli),
                                 'engine_name': name, 'revision': REVISION})
    probe = source / mixed.PROBE
    original, stamp = probe.read_bytes(), probe.stat()
    baseline = directory.state()
    active_move = active_mixed = active_reorg = owner = None
    samples, outputs = [], {}
    try:
        for flow in FLOWS:
            if flow == 'edit':
                probe.write_bytes(original + f'\n// filesync-share-{nonce}-r{round_number}\n'.encode())
                os.utime(probe, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + round_number * 1_000_000_000))
            elif flow == 'move':
                state = directory.state()
                parent = str(Path(directory.DIRECTORY).parent / f'move-{nonce}-r{round_number}')
                active_move = directory.DirectoryMove(state, parent, stamp.st_mtime_ns + round_number * 1_000_000_000)
                active_move.move()
            elif flow == 'restore-move':
                active_move.restore()
            elif flow in ('mixed', 'reorganization'):
                cls = mixed.MixedFixture if flow == 'mixed' else reorg.ReorgFixture
                fixture = cls.prepare(source, root, f'{nonce}-r{round_number}-{flow}')
                if flow == 'mixed':
                    active_mixed = fixture
                else:
                    active_reorg = fixture
                fixture.apply()
            elif flow == 'restore-mixed':
                active_mixed.restore()
            elif flow == 'restore-reorganization':
                active_reorg.restore()
            output = runtime / flow
            output.mkdir()
            before = directory.state()
            save(output / 'source.json', before)
            if owner:
                (output / 'stale.wcprof').write_bytes(command(
                    ['docker', 'exec', owner['Id'], '/tmp/cas-debug-get', '/debug/wcprof/dump']))
            record = {'flow': flow, 'arm': arm, 'round': round_number,
                      'pressure_before': {key: Path('/proc/pressure', key).read_text() for key in ('cpu', 'io', 'memory')}}
            argv = [cli, '--profile', 'api', 'query', '-M', '--doc', HERE / 'historical/import.graphql',
                    '--var-json', json.dumps({'path': str(source), 'probe': mixed.PROBE})]
            record['started_ns'] = time.time_ns()
            start = time.perf_counter_ns()
            result = subprocess.run(list(map(str, argv)), env=env, cwd=source, capture_output=True, timeout=300)
            record['cli_ms'] = (time.perf_counter_ns() - start) / 1e6
            record['process_ended_ns'] = time.time_ns()
            (output / 'stdout').write_bytes(result.stdout)
            (output / 'stderr').write_bytes(result.stderr)
            save(output / 'timing.json', {**record, 'exit_code': result.returncode})
            need(result.returncode == 0, f'CLI failed; see {output}')
            data = json.loads(result.stdout)['host']['directory']
            need(data['file']['contents'].encode() == probe.read_bytes(), 'stale probe contents')
            need(directory.state() == before, 'source changed during capture')
            relation = ('cold' if flow == 'unchanged' else flow.removeprefix('repeat-')
                        if flow.startswith('repeat-') else 'edit' if flow.startswith('restore-') else None)
            if relation:
                need(data['digest'] == outputs[relation], f'digest mismatch: {flow}')
            elif flow != 'cold':
                need(data['digest'] != outputs['cold' if flow == 'edit' else 'edit'], 'edit did not invalidate')
            outputs[flow] = data['digest']
            source_hash = digest(output / 'source.json')
            expected = references.setdefault(flow, (source_hash, data['digest']))
            need(expected == (source_hash, data['digest']), 'cross-arm source/output mismatch')
            current = inspect(name)
            need(current['Name'] == '/' + name and current['Image'] == image_id, 'engine identity differs')
            need(owner is None or current['Id'] == owner['Id'], 'engine replaced mid-run')
            owner = current
            save(output / 'owner.json', {'id': owner['Id'], 'name': name, 'image': image_id})
            if flow == 'cold':
                command(['docker', 'cp', args.debug_get, owner['Id'] + ':/tmp/cas-debug-get'])
            record.update(profile(output, owner, env, record, args.analyzer))
            record['engine_ms'] = record['class_ms']['session.serveQuery']
            record['pressure_after'] = {key: Path('/proc/pressure', key).read_text() for key in ('cpu', 'io', 'memory')}
            save(output / 'sample.json', record)
            samples.append(record)
            print(f'{arm} r{round_number} {flow}: engine={record["engine_ms"]:.1f}ms CLI={record["cli_ms"]:.1f}ms', flush=True)
            if round_number == 1 and flow in ('repeat-edit', 'repeat-move', 'repeat-mixed', 'repeat-reorganization'):
                destination = output / 'export'
                command([cli, 'api', 'query', '-M', '--doc', HERE / 'historical/import_export.graphql',
                         '--var-json', json.dumps({'path': str(source), 'output': str(destination)})], env=env, cwd=source, timeout=300)
                actual = manifest(destination)
                # Historical export normalized modes. Keep them visible; validate bytes/types/links/names.
                content = lambda tree: {key: {k: v for k, v in item.items() if k != 'mode'} for key, item in tree.items()}
                need(content(actual) == content(before['manifest']), 'full-tree readback differs')
                save(output / 'readback.json', {'content_equal': True, 'modes_equal': actual == before['manifest']})
        return samples
    finally:
        # Stop only this run's recorded engine; preserve container, volume and evidence.
        if owner:
            command(['docker', 'stop', '--time', '30', owner['Id']], timeout=60)
            (runtime / 'engine.log').write_bytes(command(['docker', 'logs', owner['Id']]))
        if active_reorg:
            active_reorg.restore()
        if active_mixed:
            active_mixed.restore()
        if active_move:
            active_move.restore()
        probe.write_bytes(original)
        os.utime(probe, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        need(directory.state() == baseline, 'fixture restoration differs; retain evidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ruff', required=True, type=Path, help='clean pinned Ruff checkout; copied, never edited')
    parser.add_argument('--output', required=True, type=Path, help='new directory; refuses existing paths')
    parser.add_argument('--arm', required=True, action='append', metavar='NAME=IMAGE')
    parser.add_argument('--rounds', type=int, default=6)
    parser.add_argument('--analyzer', required=True, type=Path, help='native wcprof-analyze executable')
    parser.add_argument('--debug-get', required=True, type=Path, help='static Linux debugget binary')
    args = parser.parse_args()
    need(args.rounds >= 1, 'rounds must be positive')
    arms = [value.split('=', 1) for value in args.arm]
    need(all(len(item) == 2 and re.fullmatch(r'[a-z][a-z0-9-]{0,20}', item[0]) for item in arms), 'invalid arm')
    need(len({item[0] for item in arms}) == len(arms), 'duplicate arm')
    args.analyzer, args.debug_get = args.analyzer.resolve(strict=True), args.debug_get.resolve(strict=True)
    source_input = args.ruff.resolve(strict=True)
    need(command(['git', '-C', source_input, 'rev-parse', 'HEAD']).decode().strip() == REVISION, 'wrong Ruff revision')
    need(not command(['git', '-C', source_input, 'status', '--porcelain']).strip(), 'Ruff is dirty')
    root = args.output.absolute()
    need(not root.resolve().is_relative_to(source_input), 'output must be outside the source checkout')
    root.mkdir(parents=True, exist_ok=False)
    root = root.resolve()
    source = root / 'ruff'
    shutil.copytree(source_input, source, symlinks=True, ignore=shutil.ignore_patterns('.git', 'target', 'dagger.toml', 'dagger.lock'))
    mixed.ROOT = reorg.ROOT = root
    directory.SOURCE = source
    nonce = secrets.token_hex(6)
    save(root / 'run.json', {'arms': arms, 'rounds': args.rounds, 'ruff': REVISION,
                           'runner_sha256': digest(__file__), 'analyzer_sha256': digest(args.analyzer),
                           'scope': 'New profiled cohort; cold engine/CLI state, warm images and OS pages; no Cargo.'})
    signal.signal(signal.SIGTERM, lambda *_: sys.exit('interrupted; retaining evidence'))
    samples = []
    for number in range(1, args.rounds + 1):
        offset = (number - 1) % len(arms)
        references = {}
        for arm, image in arms[offset:] + arms[:offset]:
            samples.extend(run_arm(args, root, source, arm, image, number, nonce, references))
    save(root / 'samples.json', samples)
    lines = ['# New filesync comparison', '', 'Medians in ms; engine / CLI. All samples retained.', '',
             '| Flow | ' + ' | '.join(arm for arm, _ in arms) + ' |',
             '| --- | ' + ' | '.join('---:' for _ in arms) + ' |']
    for flow in FLOWS:
        cells = []
        for arm, _ in arms:
            group = [row for row in samples if row['arm'] == arm and row['flow'] == flow]
            cells.append(' / '.join(f'{statistics.median(row[key] for row in group):.1f}' for key in ('engine_ms', 'cli_ms')))
        lines.append('| ' + flow + ' | ' + ' | '.join(cells) + ' |')
    (root / 'RESULTS.md').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
