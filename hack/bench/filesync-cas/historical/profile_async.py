#!/usr/bin/env python3
"""Async-aware sibling of the frozen profile_import.py; no historical edits."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time

import build
import profile_windows
from source_manifest import manifest

ROOT = build.ROOT
SOURCE = ROOT / 'ruff'
DEBUG = Path('/tmp/dagger-cli-readiness-auto.C70FUvMf/debug-get')
ANALYZER = Path('/tmp/dagger-rust-wcprof-current')
GUARD = Path('/tmp/dagger-rust-names-e2e-v2.E8b70Suk/ownership.py')
RAW = Path('/tmp/dagger-filesync-flat.c5ihvUc6/benchmarks/bench/filesync/summarize_dump.py')
PINS = {
    DEBUG: 'd50874b7f7c0235bececcb4dbad34655dcadf06452cc3f767d11a9b6160cc5d8',
    ANALYZER: 'a99a6990e378ff0fac7f6e2f4d704e862035e6f28fb1456cbe493ed55a2284f2',
    GUARD: 'd83e95cb3a61e6fdd9d945803a5ef85b9861b3e774fb08b48aaf5b4d3ec9cf99',
    RAW: 'e2ff4d098b51583a6c85c69ac69c1a763f79d601fe58d6ab8fc8b388bd0bdd48',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    def label(value):
        if value in ('initial', 'exact', 'leaf1', 'leaf1-exact', 'leaf2', 'revert') or re.fullmatch(r'ab[1-6]-(edit|exact)', value):
            return value
        raise argparse.ArgumentTypeError('unknown capture label')
    parser.add_argument('label', type=label)
    parser.add_argument('--same-as')
    parser.add_argument('--different-from')
    parser.add_argument('--parity-with', help='Owned main receipt for identical source, relative to experiment root')
    parser.add_argument('--attempt', type=int, choices=range(1, 129), default=1)
    args = parser.parse_args()
    RUNTIME = ROOT / ('runtime' if args.attempt == 1 else f'runtime-r{args.attempt}')
    assert json.loads((RUNTIME/'cli/config/dagger/engine.json').read_text()) == {'logLevel': 'debug'}
    CLI = RUNTIME / 'dagger'
    NAME = f'dagger-storage-host-efb1uyhh-r{args.attempt}-engine'
    for path, expected in PINS.items():
        assert build.sha(path) == expected, str(path)
    spec = importlib.util.spec_from_file_location('cas_ownership', GUARD)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    spec = importlib.util.spec_from_file_location('cas_raw_diagnostic', RAW)
    raw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(raw)
    env = build.environment()
    for category in ('CONFIG', 'CACHE', 'DATA', 'STATE'):
        env['XDG_' + category + '_HOME'] = str(RUNTIME / 'cli' / category.lower())
    env['DAGGER_NO_NAG'] = '1'
    env['_DAGGER_FILESYNC_PHASE_PROFILE'] = '1'
    read = lambda argv: build.read(argv, env)
    image = json.loads((RUNTIME / 'image.json').read_text())
    assert build.sha(CLI) == image['cli_sha256']
    env['DAGGER_ENGINE'] = 'image+docker://' + image['tag'] + '?container=' + NAME + '&volume=' + NAME + '&cleanup=false'
    assert read(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']) == 'c2cd236b9cc5b2149c74247e179d6567ec74066f'
    assert not (SOURCE / '.git/objects/info/alternates').exists()
    probe = SOURCE / 'crates/ruff/src/lib.rs'
    expected_contents = probe.read_text()
    out = RUNTIME / args.label
    out.mkdir(exist_ok=False)
    source_manifest = manifest(SOURCE)
    manifest_path = out / 'source-manifest.json'
    manifest_path.write_text(json.dumps(source_manifest, sort_keys=True) + '\n')
    def selected(kind, name, fields):
        template = '{' + ','.join(json.dumps(k) + ':{{json .' + k + '}}' for k in fields) + '}'
        return json.loads(read(['docker', kind, 'inspect', name, '--format', template]))
    owner_path = RUNTIME / 'owner.json'
    owner = json.loads(owner_path.read_text()) if owner_path.exists() else None
    if owner is None:
        for kind in ('container', 'volume'):
            found = subprocess.run(['docker', kind, 'inspect', NAME], env=env, capture_output=True, text=True, timeout=30)
            assert found.returncode != 0 and 'no such' in found.stderr.lower(), 'refuse an unowned existing resource'
    def identity():
        row = selected('container', NAME, ('Id', 'Name', 'Image', 'Mounts', 'State.Running', 'State.Pid', 'State.StartedAt', 'RestartCount'))
        owned = guard.engine(row, NAME, image['id'], RUNTIME / 'cli/config/dagger/engine.json', owner['engine'] if owner else None)
        volume = guard.volume(selected('volume', NAME, ('Name', 'Driver', 'Mountpoint', 'CreatedAt', 'Scope', 'Options', 'Labels')), owned, owner['volume'] if owner else None)
        assert row['State.Running']
        return {'engine': owned, 'volume': volume}
    if owner:
        identity()
    argv = [str(CLI), '--profile', 'api', 'query', '-M', '--doc', str(ROOT / 'import.graphql'),
            '--var-json', json.dumps({'path': str(SOURCE), 'probe': str(probe.relative_to(SOURCE))})]
    record = {'status': 'running', 'argv': argv, 'label': args.label,
              'scope': 'Profiled standalone Host.directory import only; no Cargo/module/native comparison.',
              'headline_eligible': False, 'controller_sha256': build.sha(__file__), 'image': image,
              'manifest_helper_sha256': build.sha(ROOT / 'source_manifest.py'),
              'source_manifest_sha256': build.sha(manifest_path),
              'probe_sha256': build.sha(probe), 'source_revision': 'c2cd236b9cc5b2149c74247e179d6567ec74066f',
              'source_diff': read(['git', '-C', str(SOURCE), 'diff', '--stat']),
              'pressure_before': {kind: Path('/proc/pressure', kind).read_text() for kind in ('cpu', 'io', 'memory')}}
    def save(): (out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    save()
    try:
        if owner:
            # Retain stale events separately; they cannot enter this sample.
            with (out / 'preflight.wcprof').open('xb') as profile:
                subprocess.run(['docker', 'exec', owner['engine']['id'], '/tmp/cas-debug-get', '/debug/wcprof/dump'],
                               env=env, stdout=profile, stderr=subprocess.PIPE, check=True, timeout=30)
        with (out / 'stdout').open('xb') as stdout, (out / 'stderr').open('xb') as stderr:
            record['started_ns'] = time.time_ns()
            tick = time.perf_counter_ns()
            result = subprocess.run(argv, cwd=SOURCE, env=env, stdin=subprocess.DEVNULL,
                                    stdout=stdout, stderr=stderr, timeout=300)
            record['milliseconds'] = (time.perf_counter_ns() - tick) / 1e6
            record['process_ended_ns'] = time.time_ns()
            record['exit_code'] = result.returncode
        assert result.returncode == 0, 'CLI failed; outputs retained'
        data = json.loads((out / 'stdout').read_text())['host']['directory']
        assert data['file']['contents'] == expected_contents, 'stale source contents'
        record['content_digest'] = data['digest']
        if args.parity_with:
            parity_path = (ROOT / args.parity_with).resolve()
            assert parity_path.is_relative_to(ROOT), 'parity reference must be owned'
            reference = json.loads(parity_path.read_text())
            assert reference['status'] == 'source-and-async-profile-validated-diagnostic-only'
            assert reference['source_revision'] == record['source_revision']
            assert reference['probe_sha256'] == record['probe_sha256'], 'parity source differs'
            if 'source_manifest_sha256' in reference:
                assert reference['source_manifest_sha256'] == record['source_manifest_sha256'], 'full parity source differs'
            record['parity_reference'] = str(parity_path)
            record['parity_reference_sha256'] = build.sha(parity_path)
            record['public_digest_matches_reference'] = data['digest'] == reference['content_digest']
            assert record['public_digest_matches_reference'], 'public directory digest differs from main'
        if args.same_as:
            assert data['digest'] == json.loads((RUNTIME / args.same_as / 'receipt.json').read_text())['content_digest']
        if args.different_from:
            assert data['digest'] != json.loads((RUNTIME / args.different_from / 'receipt.json').read_text())['content_digest']
        owned = identity()
        if owner is None:
            owner_path.write_text(json.dumps(owned, indent=2) + '\n')
            subprocess.run(['docker', 'cp', str(DEBUG), owned['engine']['id'] + ':/tmp/cas-debug-get'], env=env,
                           check=True, capture_output=True, timeout=30)
        record['admission_capture'] = profile_windows.capture(out, owned['engine']['id'], env, record['process_ended_ns'])
        with (out / 'analysis.txt').open('xb') as analysis:
            result = subprocess.run([str(ANALYZER), str(out / 'profile.wcprof')], env=env,
                                    stdout=analysis, stderr=subprocess.STDOUT, timeout=60)
            record['analyzer_exit_code'] = result.returncode
        assert result.returncode == 0, 'wcprof analysis rejected; retain profile'
        text = (out / 'analysis.txt').read_text()
        header, events, validation = raw.read_dump((out / 'profile.wcprof').read_text())
        ops = [e for e in events if e['e'] == 'op']
        counts_match = re.search(r'ops:\s*(\d+)\s+roots:\s*(\d+)\s+open at dump:\s*(\d+)\s+dropped events:\s*(\d+)', text)
        drift_match = re.search(r'simulated baseline makespan:.*?\(drift vs actual:\s*([+-]?[\d.]+)%\)', text)
        counts = list(map(int, counts_match.groups())) if counts_match else None
        drift = float(drift_match.group(1)) if drift_match else None
        window_gates, tail = profile_windows.validate(record, header, events)
        record['admission_tail'] = tail
        record['window_helper_sha256'] = build.sha(ROOT / 'profile_windows.py')
        gates = {
            'analyzer_exit_zero': result.returncode == 0,
            'header_event_count_exact': header['event_count'] == len(events),
            'native_no_drops': header['dropped_events'] == 0,
            'native_no_open_ops': not header.get('open_ops', []),
            'analyzer_counts_match': counts is not None and counts[0] == len(ops) and counts[2:] == [0, 0],
            'maintained_replay_within_2_percent': drift is not None and abs(drift) <= 2.0,
            **window_gates,
            'probe_unchanged_during_capture': build.sha(probe) == record['probe_sha256'],
            'full_source_unchanged_during_capture': manifest(SOURCE) == source_manifest,
        }
        record.update(native_analyzer_gates=gates, replay_drift_percent=drift,
                      profile_sha256=build.sha(out / 'profile.wcprof'), supplemental_raw_validation=validation,
                      classes=raw.class_summary(ops, header['strings']))
        assert all(gates.values()), 'profile acceptance failed; retain raw profile and gates'
        identity()
        record['status'] = 'source-and-async-profile-validated-diagnostic-only'
        record['owner'] = owned
        walks = []
        for line in (out / 'stderr').read_text().splitlines():
            start = line.find('{"kind":"filesync.client.walk"')
            if start >= 0:
                value, _ = json.JSONDecoder().raw_decode(line[start:])
                keys = ('enumerate_filter_ns', 'entry_info_ns', 'packet_bookkeeping_ns', 'stat_send_ns')
                assert not value['failed'] and sum(value[key] for key in keys) == value['walk_ns']
                walks.append(value)
        assert walks and max(value['entries'] for value in walks) >= 12025
        record['phase_diagnostics'] = {'client_walks': walks, 'status': 'client-partitions-validated'}
    except BaseException as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        if not owner_path.exists():
            # A failed initial command may have provisioned the uniquely named
            # engine. Preserve verified ownership so the caller can stop it.
            try:
                owner_path.write_text(json.dumps(identity(), indent=2) + '\n')
            except Exception as recovery_error:
                record['ownership_recovery_error'] = repr(recovery_error)
        record['ended_ns'] = time.time_ns()
        record['pressure_after'] = {kind: Path('/proc/pressure', kind).read_text() for kind in ('cpu', 'io', 'memory')}
        save()
    print(json.dumps({key: record[key] for key in ('label', 'milliseconds', 'content_digest', 'status')}), flush=True)

if __name__ == '__main__':
    main()
