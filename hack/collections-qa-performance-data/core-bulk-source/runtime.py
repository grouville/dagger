"""LOCAL-only ABBA process-restart comparison of the core metadata bulk consumer.

Dry-run by default. 36 ordinary commands (28 measured, 8 primers), then two
separate first-API wcprof diagnostics. One retained task-owned volume; never a
cold-volume test. The original engine binary is restored and stopped in finally.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, os, re, shutil, signal, subprocess, sys, threading, time
HERE = Path(__file__).resolve().parent
LAB = Path('/tmp/collections-perf/engine-allocation-round2')
sys.path.insert(0, str(LAB))
import experiment as x
spec = importlib.util.spec_from_file_location('navigation', LAB/'navigation-generate.py')
nav = importlib.util.module_from_spec(spec); spec.loader.exec_module(nav)
OWNER = 'collections-lazy-core-runtime-v1'
ORIGINAL_SHA = '56f2eaccf6bf2f3151fb4c08205e1ad33fa7730ad5dee32577e867b527fc4b12'
CLI = Path('/tmp/collections-perf/cli-log-overlap-v3/backport-v016/builds/dagger-baseline')
CLI_SHA = '748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30'
ENGINE_SHA = {
    'baseline': 'f864931c4dab6c53f7a1b552eace782eaf925e4dfa600bd5aa57a0099cb5189b',
    'candidate': '81b6b4b44b59527044ec3fde8376a66af6666d57711e63d15a03bc0592e22645',
}
FLOWS = {'core': ['-m', 'core', 'api', 'call', 'version'],
         'module': ['-m', './module', 'api', 'call', 'read'],
         'listing': ['check', '-l', '--all']}
MIN_FREE = 16*1024**3
MAX_WRITE = 4*1024**3
CAP = 38

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--output', default='runtime-v1')
    a = p.parse_args()
    assert re.fullmatch(r'runtime-v[0-9]+', a.output)
    out = HERE/a.output
    if not a.run:
        print(json.dumps({'execute': False, 'cloud_commands': 0, 'local_commands_cap': CAP,
            'ordinary_measured': 28, 'ordinary_primers': 8, 'profiled_diagnostics': 2,
            'ordinary_blocks': ['baseline', 'candidate', 'candidate', 'baseline'],
            'first_call': 'core API after process restart, retained shared volume; cache may persist',
            'warm': 'two repetitions per flow after explicit module/listing primers',
            'diagnostics': 'one additional restart and first core API profile per variant after ordinary blocks',
            'output': str(out), 'same_cli_sha256': CLI_SHA,
            'engine_manifest': str(HERE/'builds/runtime-builds.json'),
            'original_binary_restored': True, 'volumes_deleted': 0}))
        return
    os.umask(0o077)
    assert not out.exists()
    assert x.sha(CLI) == CLI_SHA
    builds = json.loads((HERE/'builds/runtime-builds.json').read_text())
    assert builds['source_head'] == '85b60f7a0a16a27459ef571bc94bcf870c876dcc'
    for name, expected in ENGINE_SHA.items():
        assert builds['variants'][name]['sha256'] == expected
        assert x.sha(builds['variants'][name]['path']) == expected
    original = json.loads((LAB/'lazy-core-runtime-v1/engines.json').read_text())['lazy']
    assert original['sha256'] == ORIGINAL_SHA
    x.OWNER = OWNER
    info = x.owned(original)
    assert not info['State']['Running']
    mounts = [m for m in info['Mounts'] if m['Destination'] == '/var/lib/dagger']
    assert len(mounts) == 1 and mounts[0]['Name'] == original['name'] and mounts[0]['Type'] == 'volume'
    volume = json.loads(x.capture(['docker', 'volume', 'inspect', mounts[0]['Name']]))[0]
    assert volume['Labels']['dagger.perf.owner'] == OWNER
    app = LAB/'greetings'; native = LAB/'native'
    first = Path('/tmp/collections-perf/sdk-edit-audit/core-typeref-intern-v1/first-consumer-local-v1')
    corecwd = first/'workspace'
    fixture_paths = {'app': app, 'native': native, 'core': corecwd}
    fixtures = {name: x.fixture_hashes(path) for name, path in fixture_paths.items()}
    assert fixtures['app'] == json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
    # Exact version from this frozen HEAD85 dirty build, not the older HEAD21939 golden.
    expected = {'core': b'v1.0.0-beta.15+85b60f7a.dirty',
                'module': (native/'input.txt').read_bytes(),
                'listing': Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()}
    cwd = {'core': corecwd, 'module': native, 'listing': app}
    out.mkdir(); (out/'empty-config').mkdir(); (out/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    env.update(XDG_CONFIG_HOME=str(out/'empty-config'), DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1', GIT_TERMINAL_PROMPT='0')
    assert not any(k in env for k in ('DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'OTEL_EXPORTER_OTLP_ENDPOINT', 'HTTP_PROXY', 'HTTPS_PROXY'))
    rows = []; attempts = []; starts = []; written = 0; modified = False
    item = dict(original); backup = out/'original-engine.private'
    x.write(out/'provenance.json', {'build_manifest': builds, 'build_manifest_sha256': x.sha(HERE/'builds/runtime-builds.json'),
        'driver_sha256': x.sha(__file__), 'cli_sha256': CLI_SHA, 'original_engine': original,
        'fixture_hashes': fixtures, 'expected_stdout_sha256': {k: hashlib.sha256(v).hexdigest() for k, v in expected.items()},
        'cloud_commands': 0, 'local_commands_cap': CAP, 'ordinary_profiling': False,
        'timing_boundary': 'CLI spawn through blocking waitpid; setup, stop/start, guards, counters and profile downloads excluded',
        'warmth': 'Retained same Dagger volume with warm host images/pages; restart each block. Not a cold-volume test. Persisted metadata may be reused.',
        'attribution': 'Separate first-API profiles determine construction/cache work; profiled CLI latency is diagnostic only.',
        'limits': {'min_free_bytes': MIN_FREE, 'max_engine_write_bytes': MAX_WRITE}})
    def guard():
        assert all(x.fixture_hashes(path) == fixtures[name] for name, path in fixture_paths.items())
        assert shutil.disk_usage(HERE).free > MIN_FREE and written < MAX_WRITE
    def restart(variant, phase, block):
        nonlocal item, modified
        guard()
        if x.owned(item)['State']['Running']:
            x.capture(['docker', 'stop', '--timeout', '30', item['name']])
        assert not x.owned(item)['State']['Running']
        modified = True
        x.capture(['docker', 'cp', builds['variants'][variant]['path'], item['name']+':/usr/local/bin/dagger-engine'])
        item = dict(original, sha256=ENGINE_SHA[variant])
        seconds = x.start(item)
        starts.append({'variant': variant, 'phase': phase, 'block': block, 'startup_seconds_excluded': seconds})
        x.write(out/'starts.json', starts)
    def run(variant, flow, phase, block, repetition=0, profile=False):
        nonlocal written
        guard(); assert len(attempts) < CAP
        dest = out/f'{len(attempts):02d}-{phase}-{block}-{repetition}-{flow}-{variant}'
        dest.mkdir()
        attempts.append({'variant': variant, 'flow': flow, 'phase': phase, 'block': block, 'repetition': repetition, 'profile': profile})
        x.write(out/'attempts.json', attempts)
        if profile:
            try: (dest/'prior.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
            except x.HTTPError as err:
                if err.code != 503: raise
        command = [str(CLI), '--engine', 'container://'+item['name']]+(['--profile'] if profile else [])+FLOWS[flow]
        before = nav.warm.snapshot(item); done = threading.Event(); ob = {}
        with (dest/'stdout.txt').open('wb') as stdout, (dest/'stderr.txt').open('wb') as stderr:
            begin = time.monotonic(); started = time.time_ns()
            proc = subprocess.Popen(command, cwd=cwd[flow], env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            def wait():
                ob.update(exit_code=proc.wait(), end=time.monotonic(), wall_end=time.time_ns()); done.set()
            worker = threading.Thread(target=wait, daemon=True); worker.start()
            timeout = not done.wait(180)
            if timeout:
                try: proc.send_signal(signal.SIGINT)
                except ProcessLookupError: pass
                if not done.wait(10):
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
            worker.join(15); assert not worker.is_alive()
        delta = nav.warm.delta(before, nav.warm.snapshot(item)); written += delta['engine_written_bytes']
        actual = (dest/'stdout.txt').read_bytes(); stderr = (dest/'stderr.txt').read_bytes()
        links = re.findall(rb'https://[^\s\x1b]*dagger.cloud/[^\s\x1b]*', actual+stderr)
        unexpected_cloud_link = any(url.rstrip(b'.') != b'https://dagger.cloud/traces/setup' for url in links)
        correct = not timeout and ob['exit_code'] == 0 and not unexpected_cloud_link and actual == expected[flow]
        row = dict(attempts[-1], seconds=ob['end']-begin, started_unix_ns=started, exited_unix_ns=ob['wall_end'],
            correct=correct, exit_code=ob['exit_code'], timed_out=timeout, stdout_sha256=x.sha(dest/'stdout.txt'),
            stdout_matches_expected=actual == expected[flow], unexpected_cloud_link=unexpected_cloud_link, **delta)
        if profile:
            (dest/'run.wcprof').write_bytes(x.get(item['port'], '/debug/wcprof/dump?flush=true'))
            row['profile_sha256'] = x.sha(dest/'run.wcprof')
        rows.append(row); x.write(out/'results.json', rows)
        print(json.dumps({k: row[k] for k in ('variant', 'flow', 'phase', 'block', 'repetition', 'seconds', 'correct')}), flush=True)
        assert correct, 'correctness failure in '+dest.name
        guard()
    try:
        guard()
        x.capture(['docker', 'cp', item['name']+':/usr/local/bin/dagger-engine', str(backup)])
        assert x.sha(backup) == ORIGINAL_SHA
        for block, variant in enumerate(('baseline', 'candidate', 'candidate', 'baseline')):
            restart(variant, 'ordinary', block)
            run(variant, 'core', 'first-api-after-restart', block)
            for flow in ('module', 'listing'): run(variant, flow, 'explicit-primer', block)
            for repetition in range(2):
                for flow in FLOWS: run(variant, flow, 'warm', block, repetition)
        for block, variant in enumerate(('baseline', 'candidate')):
            restart(variant, 'separate-profile', block)
            run(variant, 'core', 'diagnostic-first-api-after-restart', block, profile=True)
    finally:
        if x.owned(item)['State']['Running']:
            x.capture(['docker', 'stop', '--timeout', '30', item['name']])
        restored = not modified
        if modified:
            assert not x.owned(item)['State']['Running'] and x.sha(backup) == ORIGINAL_SHA
            x.capture(['docker', 'cp', str(backup), item['name']+':/usr/local/bin/dagger-engine'])
            check = out/'restored-engine.private'
            x.capture(['docker', 'cp', item['name']+':/usr/local/bin/dagger-engine', str(check)])
            restored = x.sha(check) == ORIGINAL_SHA
        unchanged = all(x.fixture_hashes(path) == fixtures[name] for name, path in fixture_paths.items())
        x.write(out/'restoration.json', {'original_binary_restored': restored, 'engine_stopped': not x.owned(item)['State']['Running'],
            'fixtures_unchanged': unchanged, 'local_attempts': len(attempts), 'validated_commands': sum(r['correct'] for r in rows),
            'cloud_commands': 0, 'resources_deleted': 0, 'volume_retained': True, 'engine_written_bytes': written})
        assert unchanged and restored
    assert len(rows) == CAP and all(r['correct'] for r in rows)
if __name__ == '__main__': main()
