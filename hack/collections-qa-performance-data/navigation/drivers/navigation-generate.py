"""Prepared bounded navigation/generation trial; executes only with --run.

Five local correctness warmups, then 3 ordinary samples and 1 separate diagnostic
profile per flow: 20 Cloud commands. Native generation is a single ordinary Dang
@generate method, not an SDK generator benchmark. No engine replacement/reset.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import threading
import time
import uuid

import experiment as x

LAB = Path(__file__).resolve().parent
OUT = LAB / 'navigation-generate-v1'
BUILD = Path('/tmp/collections-perf/cli-exit-tail-v2')
LIMIT = 20
FLOWS = {
    'workspace-files': ['ws', 'ls'],
    'artifacts': ['list', '-a'],
    'generators': ['generate', '-l'],
    'generate-warm': ['-y', 'generate'],
    'generate-edit': ['-y', 'generate'],
}
spec = importlib.util.spec_from_file_location('warm', LAB / 'withfile-cloud-warm.py')
warm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(warm)
ANSI = re.compile(rb'\x1b\[[0-9;]*[A-Za-z]')


def normalize(contents):
    return sorted(b' '.join(line.split()) for line in ANSI.sub(b'', contents).splitlines() if line.strip())


def known_listing(flow, contents):
    lines = normalize(contents)
    if flow == 'workspace-files':
        return all(entry in lines for entry in (b'main.go', b'main_test.go', b'dagger.toml', b'go.mod', b'website/'))
    if flow == 'artifacts':
        return all(any(key in line for line in lines) for key in (b'go/modules', b'backend/', b'frontend/'))
    if flow == 'generators':
        return all(any(key in line for line in lines) for key in (b'dagger-go-sdk/generate', b'dagger-typescript-sdk/generate', b'go/modules/generate'))
    raise ValueError('unknown listing flow')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'execute': False, 'cloud_commands_max': LIMIT, 'local_correctness_warmups': 5,
                          'engine_starts_max': 1, 'flows': FLOWS, 'output': str(OUT),
                          'scope': 'native generate is not SDK code generation'}))
        return
    os.umask(0o077)
    assert not OUT.exists(), 'never resume or overwrite a partial trial'
    state = json.loads((LAB / 'withfile-v1/prepared.json').read_text())
    prior = json.loads((LAB / 'exit-tail-diagnostic-v1/results.json').read_text())
    assert (LAB / 'exit-tail-diagnostic-v1/summary.json').is_file(), 'prior normal-login trial incomplete'
    assert any(row['production'] and row['correct'] and row['cloud_link_visible'] for row in prior), 'prior normal-login control missing'
    app, native = LAB / 'greetings', LAB / 'native'
    assert x.fixture_hashes(app) == state['input_sha256'], 'greetings fixture changed'
    native_hashes = x.fixture_hashes(native)
    original = {name: (native / name).read_bytes() if (native / name).exists() else None
                for name in ('input.txt', 'generated.txt')}
    assert original['input.txt'] is not None
    binaries = {key: BUILD / ('dagger-' + key) for key in ('control', 'diagnostic')}
    builds = json.loads((BUILD / 'build-results.json').read_text())
    for entry in builds['builds']:
        assert entry['exitCode'] == 0 and x.sha(binaries[entry['name']]) == entry['sha256']
    assert shutil.disk_usage(LAB).free > 16 * 1024**3
    OUT.mkdir(mode=0o700)
    (OUT / 'driver.py.txt').write_bytes(Path(__file__).read_bytes())
    common = {key: os.environ[key] for key in ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR') if key in os.environ}
    common.update(DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1', GIT_TERMINAL_PROMPT='0')
    local = dict(common, XDG_CONFIG_HOME=str(LAB / 'empty-config'))
    cloud = dict(common, DAGGER_CLOUD_URL='https://api.dagger.cloud')
    for key in ('DAGGER_CLOUD_TOKEN', 'XDG_CONFIG_HOME'):
        if key in os.environ:
            cloud[key] = os.environ[key]
    item = state['candidate']
    startup = x.start(item)
    x.write(OUT / 'provenance.json', {
        'engine': item, 'engine_start_seconds_excluded': startup,
        'cli_sha256': {key: x.sha(path) for key, path in binaries.items()},
        'source_manifest_sha256': x.sha(BUILD / 'source-manifest.json'),
        'driver_sha256': x.sha(__file__), 'flows': FLOWS,
        'cloud_commands_max': LIMIT, 'local_correctness_warmups': 5,
        'authentication': 'ordinary user login and explicit production endpoint; no credential-file reads by driver',
        'cache_boundary': 'retained candidate engine; no cold claim; warmups separate from ordinary samples',
        'generation_scope': 'single native Dang @generate writing input.txt contents; not Go/TS/Python SDK generation',
        'fixture_hashes_before': native_hashes,
        'measurement': 'fresh CLI spawn through blocking waitpid; file bytes polled every 5 ms; counters/profile dumps outside ordinary timing',
        'privacy': 'raw outputs and wcprof private; shared results contain timings, counts and validation booleans only',
    })
    rows, attempts, expected_listings = [], [], {}
    nonce = uuid.uuid4().hex
    expected_native = dict(native_hashes)

    def guard():
        assert x.fixture_hashes(app) == state['input_sha256'], 'greetings fixture changed'
        assert x.fixture_hashes(native) == expected_native, 'native fixture changed unexpectedly'
        assert shutil.disk_usage(LAB).free > 16 * 1024**3

    def native_input(contents):
        (native / 'input.txt').write_bytes(contents)
        expected_native['input.txt'] = hashlib.sha256(contents).hexdigest()

    def run(flow, phase, index, production, diagnostic=False):
        assert not production or sum(row['production'] for row in attempts) < LIMIT
        guard()
        generates = flow.startswith('generate-')
        if generates:
            if flow == 'generate-edit':
                contents = f'navigation-generate {nonce} {phase} {index}\n'.encode()
            else:
                contents = original['input.txt']
            native_input(contents)
            (native / 'generated.txt').unlink(missing_ok=True)
            expected_native.pop('generated.txt', None)
        else:
            contents = None
        guard()
        dest = OUT / f'{phase}-{index}-{flow}'
        dest.mkdir()
        env = dict(cloud if production else local)
        if diagnostic:
            env['DAGGER_PERF_EXIT_TIMELINE'] = str(dest / 'timeline.jsonl')
            try:
                (dest / 'prior.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
            except x.HTTPError as error:
                if error.code != 503:
                    raise
        command = [str(binaries['diagnostic' if diagnostic else 'control']), '--engine', 'container://' + item['name']]
        command += (['--profile'] if diagnostic else []) + FLOWS[flow]
        attempt = dict(flow=flow, phase=phase, index=index, production=production,
                       diagnostic=diagnostic, profile=diagnostic, command=command)
        attempts.append(attempt)
        x.write(OUT / 'attempts.json', attempts)
        before = warm.snapshot(item)
        done, observed = threading.Event(), {}
        visible, polls = None, 0
        with (dest / 'stdout.txt').open('wb') as stdout, (dest / 'stderr.txt').open('wb') as stderr:
            begin, wall = time.monotonic(), time.time_ns()
            process = subprocess.Popen(command, cwd=native if generates else app, env=env,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            def waiter():
                observed['status'] = process.wait()
                observed['time'], observed['wall'] = time.monotonic(), time.time_ns()
                done.set()
            worker = threading.Thread(target=waiter, daemon=True)
            worker.start()
            timed_out = False
            try:
                if generates:
                    while not done.is_set() and time.monotonic() - begin < 240:
                        polls += 1
                        try:
                            if (native / 'generated.txt').read_bytes() == contents:
                                visible = time.monotonic()
                                break
                        except FileNotFoundError:
                            pass
                        done.wait(.005)
                timed_out = not done.wait(max(0, 240 - (time.monotonic() - begin)))
            finally:
                if not done.is_set():
                    process.send_signal(signal.SIGINT)
                    if not done.wait(10):
                        os.killpg(process.pid, signal.SIGKILL)
                worker.join(timeout=15)
                assert not worker.is_alive(), 'owned CLI did not exit'
        after = warm.snapshot(item)
        stdout, stderr = (dest / 'stdout.txt').read_bytes(), (dest / 'stderr.txt').read_bytes()
        correct = not timed_out and observed['status'] == 0
        if generates:
            generated = (native / 'generated.txt').read_bytes() if (native / 'generated.txt').exists() else None
            correct &= generated == contents
            if generated is not None:
                expected_native['generated.txt'] = hashlib.sha256(generated).hexdigest()
            # If exit won the last 5 ms polling race, final equality is still
            # correctness proof; readiness is right-censored at process exit.
        else:
            correct &= known_listing(flow, stdout)
            normalized = normalize(stdout)
            if not production:
                expected_listings[flow] = normalized
            else:
                correct &= normalized == expected_listings[flow]
        timeline = []
        if diagnostic:
            timeline = [json.loads(line) for line in (dest / 'timeline.jsonl').read_text().splitlines()]
            correct &= bool(timeline) and any(row['kind'] == 'cli.command' for row in timeline)
            correct &= timeline[-1].get('values', {}).get('dropped_events') == 0
            uploads = [row for row in timeline if row['kind'] in ('cloud.traces', 'cloud.logs', 'cloud.metrics')]
            correct &= bool(uploads) and all(200 <= row.get('values', {}).get('status', 0) < 300 for row in uploads)
        row = dict(attempt, seconds=observed['time'] - begin, started_unix_ns=wall,
                   exited_unix_ns=observed['wall'], exit_code=observed['status'], timed_out=timed_out,
                   correct=bool(correct), stdout_sha256=x.sha(dest / 'stdout.txt'), stderr_bytes=len(stderr),
                   cloud_link_visible=bool(re.search(rb'https://[^\s]*dagger.cloud/', stdout + stderr)),
                   file_visible_seconds=visible - begin if visible is not None else None,
                   file_visibility_censored_at_exit=bool(generates and visible is None and correct),
                   file_visibility_poll_ms=5 if generates else None, file_poll_count=polls,
                   generated_bytes=len(contents) if generates and correct else None,
                   timeline_events=len(timeline), before=before, after=after, **warm.delta(before, after))
        rows.append(row)
        attempt['correct'] = bool(correct)
        x.write(OUT / 'attempts.json', attempts)
        x.write(OUT / 'results.json', rows)
        print(json.dumps({key: row[key] for key in ('phase', 'flow', 'index', 'seconds', 'file_visible_seconds', 'correct')}), flush=True)
        if diagnostic:
            (dest / 'run.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
        assert correct, 'command/output validation failed; inspect private artifacts'
        guard()
        time.sleep(1)

    try:
        for flow in FLOWS:
            run(flow, 'local-correctness', 0, False)
        for index in range(3):
            for flow in FLOWS:
                run(flow, 'ordinary', index, True)
        for flow in FLOWS:
            run(flow, 'diagnostic', 0, True, diagnostic=True)
    finally:
        for name, contents in original.items():
            if contents is None:
                (native / name).unlink(missing_ok=True)
            else:
                (native / name).write_bytes(contents)
        restored = x.fixture_hashes(native) == native_hashes
        greetings_unchanged = x.fixture_hashes(app) == state['input_sha256']
        x.write(OUT / 'fixture-validation.json', {
            'native_full_fixture_restored': restored, 'greetings_full_fixture_unchanged': greetings_unchanged,
            'commands_attempted': len(attempts), 'cloud_commands_attempted': sum(row['production'] for row in attempts),
            'commands_validated': sum(row['correct'] for row in rows),
        })
        assert restored and greetings_unchanged, 'full fixture restoration mismatch'
    assert len(rows) == 25 and all(row['correct'] for row in rows)
    summary = {'all_correct': True, 'cloud_commands': LIMIT, 'local_correctness_warmups': 5,
               'sdk_generator_benchmark': False, 'flows': {}}
    for flow in FLOWS:
        selected = [row for row in rows if row['flow'] == flow and row['phase'] == 'ordinary']
        summary['flows'][flow] = {'seconds': [row['seconds'] for row in selected],
                                  'median_seconds': statistics.median(row['seconds'] for row in selected),
                                  'file_visible_seconds': [row['file_visible_seconds'] for row in selected]}
    x.write(OUT / 'summary.json', summary)


if __name__ == '__main__':
    main()
