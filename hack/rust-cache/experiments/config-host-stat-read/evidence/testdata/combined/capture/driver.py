from pathlib import Path
import gzip
import hashlib
import json
import os
import signal
import subprocess
import threading
import time
import urllib.request

protocol = Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
exec(protocol.read_text().split('fixtures = [f for f')[0])
cli = base / 'config-host-stat-read/dagger'
workspace = Path('/tmp/dagger-go-real-repository-main')
module = Path('/tmp/dagger-go-module-test-name-index')
source = workspace / 'dagql/types.go'
original = source.read_bytes()
configs = {n: (workspace/n).read_bytes() if (workspace/n).exists() else None for n in ['dagger.toml', 'dagger.lock']}
routes = ['batch-metadata', 'attribute-array-decode', 'reusable-declarations', 'span-lookup-fanout',
          'span-resource-batches', 'lazy-type-maps', 'telemetry-flush-coalescing',
          'callback-caller-reuse', 'otel-evicted-queue', 'single-toml-parse', 'parallel-client-admission', 'prepared-schema', 'restored-posting-removal', 'usage-sampling', 'builtin-receivers', 'config-declarations', 'config-stat-read']
flags = {route: get(route)['enabled'] for route in routes}
seed_path = '/tmp/filesync-snapshot-seeds-mode'
seeds = subprocess.check_output(['docker', 'exec', record['Id'], 'cat', seed_path])
env['CPUPROFILE'] = str(root/'cli-cpu.pprof')
env.pop('PPROF', None)
env['_EXPERIMENTAL_DAGGER_VERSION'] = 'v1.0.0-beta.15'

def raw(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()

stop = threading.Event()
samples, windows, errors, threads = [], [], [], []

def sample():
    while not stop.wait(1):
        samples.append(dict(seconds=time.monotonic()-tick, heap=heap(), engine_cpu=cpu(), pressure=pressure()))

def engine_cpu():
    index = 0
    while not stop.is_set():
        begin = time.monotonic()
        try:
            data = raw(debug+'pprof/profile?seconds=5', 20)
            name = f'engine-cpu-{index:03d}.pprof'
            (root/name).write_bytes(data)
            end = time.monotonic()
            snapshots = {}
            for kind in ['mutex', 'block', 'goroutine']:
                snapshot_begin = time.monotonic()
                filename = f'{kind}-{index:03d}.pprof'
                payload = raw(debug+'pprof/'+kind, 30)
                (root/filename).write_bytes(payload)
                snapshots[kind] = dict(path=filename, start_seconds=snapshot_begin-tick, end_seconds=time.monotonic()-tick, bytes=len(payload))
            windows.append(dict(path=name, start_seconds=begin-tick, end_seconds=end-tick, bytes=len(data), snapshots=snapshots))
        except Exception as error:
            errors.append(dict(scope='windowed_profiles', start_seconds=begin-tick, error=str(error)))
            break
        index += 1

assert not get('wcprof/enabled')['global_enabled']
assert not get('snapshot-collection')['deferred']
assert get('collection-expansion-limit')['limit'] == 0
idle('profile-publication-waits')
assert get('lock-profiler') == dict(mutex_fraction=0, block_profile_rate_ns=0)
metadata = dict(
    scope='Diagnostic full Go listing with combined host stat/read enabled after its complete-command regression, with complete wcprof, five-second CPU windows and aligned cumulative mutex/block/goroutine snapshots. This is wait attribution, not a latency benchmark. Normal telemetry, validation and GC; rejected prepared-schema and parallel-client-admission experiments stay off. Linear restored-posting removal is common with the preceding cohort.',
    cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
    engine_sha256=subprocess.check_output(['docker', 'exec', record['Id'], 'sha256sum', '/usr/local/bin/dagger-engine'], text=True).split()[0],
    workspace_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=workspace, text=True).strip(),
    module_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=module, text=True).strip(),
    warm_engine=True, fresh_cli=True, fresh_source_edit=True, telemetry=True, ordinary_gc=True,
    allocation_profiles="Cumulative allocs before and after the diagnostic command, no forced GC. Profiles are sampled and may lag recent allocations until subsequent normal GC cycles.", cpu_profile_window_seconds=5, cli_cpu_profiling=True, cli_runtime_trace=True, engine_runtime_trace=False, flags_before=flags, mutex_sample_fraction=10, block_profile_rate_ns=1000000)
(root/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
cancelled = False
try:
    for route in ['batch-metadata', 'attribute-array-decode', 'reusable-declarations', 'span-lookup-fanout', 'usage-sampling', 'builtin-receivers', 'config-declarations', 'config-stat-read']:
        mode(route, True)
    for route in ['span-resource-batches', 'lazy-type-maps', 'telemetry-flush-coalescing', 'callback-caller-reuse', 'otel-evicted-queue', 'single-toml-parse', 'parallel-client-admission', 'prepared-schema']:
        mode(route, False)
    mode('restored-posting-removal', True)
    get('span-lookup-fanout?record=false', b'')
    get('config-declarations?enabled=true&record=false',b'')
    get('builtin-receivers?enabled=true&record=false',b'')
    get('span-resource-batches?record=false', b'')
    subprocess.run(['docker', 'exec', '-i', record['Id'], 'sh', '-c', 'cat > '+seed_path], input=b'on\n', check=True)
    source.write_bytes(original+f'\n// Profile combined host stat and read regression {time.time_ns()}\n'.encode())
    (workspace/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
    get('wcprof/enabled', b'on')
    raw(debug+'wcprof/dump')
    snapshot_before = get('snapshot-collection')
    declarations_before = get('reusable-declarations')
    (root/'engine-allocs-before.pprof').write_bytes(raw(debug+'pprof/allocs', 30))
    before = heap()
    before_cpu = cpu()
    before_pressure = pressure()
    for kind in ['mutex','block']:
        (root/(kind+'-before.pprof')).write_bytes(raw(debug+'pprof/'+kind))
    lock_state=get('lock-profiler?enabled=true',b'')
    assert lock_state == dict(mutex_fraction=10,block_profile_rate_ns=1000000),lock_state
    tick, wall = time.monotonic(), time.time()
    command = [str(cli), 'check', '--module', 'go', '--check', 'test', '--list', '--all']
    timed = ['/usr/bin/time', '-f', '{"user_seconds":%U,"system_seconds":%S,"max_rss_kib":%M}', '-o', str(root/'cli-resources.json'), '--', *command]
    with (root/'command.stdout').open('w') as out, (root/'command.stderr').open('w') as err:
        process = subprocess.Popen(timed, cwd=workspace, env=env, stdout=out, stderr=err, start_new_session=True)
        threads = [threading.Thread(target=sample), threading.Thread(target=engine_cpu)]
        for thread in threads:
            thread.start()
        try:
            code = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            cancelled = True
            os.killpg(process.pid, signal.SIGINT)
            code = process.wait()
    elapsed = time.monotonic()-tick
    after, after_cpu, after_pressure = heap(), cpu(), pressure()
    (root/'engine-allocs-after.pprof').write_bytes(raw(debug+'pprof/allocs', 30))
    snapshot_after = get('snapshot-collection')
    declarations_after = get('reusable-declarations')
finally:
    stop.set()
    lock_state=get('lock-profiler?enabled=false',b'')
    assert lock_state == dict(mutex_fraction=0,block_profile_rate_ns=0),lock_state
    for kind in ['mutex','block']:
        (root/(kind+'-after.pprof')).write_bytes(raw(debug+'pprof/'+kind))
    get('wcprof/enabled', b'off')
    for thread in threads:
        thread.join()
    source.write_bytes(original)
    for name, data in configs.items():
        if data is None:
            (workspace/name).unlink(missing_ok=True)
        else:
            (workspace/name).write_bytes(data)
    for route, enabled in flags.items():
        mode(route, enabled)
    subprocess.run(['docker', 'exec', '-i', record['Id'], 'sh', '-c', 'cat > '+seed_path], input=seeds, check=True)

(root/'samples.json').write_text(json.dumps(samples, indent=2)+'\n')
(root/'engine-cpu-windows.json').write_text(json.dumps(windows, indent=2)+'\n')
chunks, events = [], []
deadline = time.monotonic()+120
while True:
    data = raw(debug+'wcprof/dump', 45)
    (root/f'wcprof-{len(chunks)}.ndjson.gz').write_bytes(gzip.compress(data, mtime=0))
    lines = data.splitlines()
    header = json.loads(lines[0])
    chunks.append(header)
    events.extend(lines[1:])
    if not header.get('open_ops'):
        break
    assert time.monotonic() < deadline, 'wcprof operations still open'
    time.sleep(1)
header = dict(chunks[-1])
header['event_count'] = len(events)
(root/'wcprof-complete.ndjson').write_bytes((json.dumps(header)+'\n').encode()+b'\n'.join(events)+b'\n')
listed = [s for s in (root/'command.stdout').read_text().splitlines() if s.startswith('go ')]
expected = [s for s in (base/'go-wide-trace-index/profile-fast/command.stdout').read_text().splitlines() if s.startswith('go ')]
result = dict(snapshot_before=snapshot_before, snapshot_after=snapshot_after, declarations_before=declarations_before, declarations_after=declarations_after, seconds=elapsed, exit_code=code, cancelled=cancelled, rows=len(listed), same_rows=listed==expected,
    engine_cpu=after_cpu-before_cpu, engine_heap_delta={k: after[k]-before[k] for k in before},
    pressure={k: (after_pressure[k]-before_pressure[k])/(elapsed*1e6) for k in before_pressure},
    cli_resources=json.loads((root/'cli-resources.json').read_text().splitlines()[-1]),
    cpu_windows=len(windows), errors=errors,
    recorder=dict(events=len(events), dropped=header['dropped_events'], open=len(header.get('open_ops', []))),
    restored_source=hashlib.sha256(source.read_bytes()).hexdigest()==hashlib.sha256(original).hexdigest(),
    unix_start=wall)
(root/'result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2), flush=True)
assert code == 0 and not cancelled and listed == expected and len(listed) == 4398
assert not header.get('open_ops') and header['dropped_events'] == 0
