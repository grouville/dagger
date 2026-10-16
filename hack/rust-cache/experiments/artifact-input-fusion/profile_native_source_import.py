from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import secrets
import statistics
import subprocess
import time
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--output-root', type=Path, required=True)
parser.add_argument('--pairs', type=int, default=8)
parser.add_argument('--profile', action='store_true')
parser.add_argument('--force-go-gc', action='store_true')
args = parser.parse_args()
root = args.output_root
root.mkdir(exist_ok=False)
base = Path('/tmp/rust-cache-sipsma-review')
source = Path('/tmp/rust-native-config-entry-1026-before')
config = source / 'dagger.toml'
original_config = config.read_text()
debug = 'http://127.0.0.1:16104/debug/'
cli = base / 'dagger-artifact-list-buffered'
module = Path('/tmp/dagger-rust-native-deep-artifact-closures')
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
engine = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
groups = {'engine': engine, 'exec': engine.parent / 'exec', 'docker_total': engine.parent}
removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
env = {k: v for k, v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://' + (base / 'otlp-null-address.txt').read_text().strip() + ':43184', DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config', NO_PROXY='*', _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')


def get(route, data=None, timeout=180):
    with urllib.request.urlopen(urllib.request.Request(debug + route, data=data), timeout=timeout) as response:
        return json.load(response)


def action(name, **options):
    return get('snapshot-collection?' + urllib.parse.urlencode(dict(action=name, **{k: str(v).lower() if isinstance(v, bool) else v for k, v in options.items()})), b'')


def mode(route, enabled):
    assert get(route + '?enabled=' + str(enabled).lower(), b'')['enabled'] == enabled


def source_mode(enabled):
    subprocess.run(['docker', 'exec', '-i', record['Id'], 'sh', '-c', 'cat > /tmp/filesync-snapshot-seeds-mode'], input=b'on\n' if enabled else b'off\n', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def pressure():
    values = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', engine)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                values[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return values


def cpu():
    return {k: next(int(line.split()[1]) for line in (p / 'cpu.stat').read_text().splitlines() if line.startswith('usage_usec ')) / 1e6 for k, p in groups.items()}


def heap():
    value = get('vars')['memstats']
    return {k: value[k] for k in ['HeapAlloc', 'HeapInuse', 'HeapIdle', 'HeapReleased', 'HeapObjects', 'TotalAlloc', 'Mallocs', 'Frees', 'NumGC', 'NextGC', 'PauseTotalNs', 'GCCPUFraction']}


def idle(label, quiet=True):
    started = time.monotonic()
    while True:
        before = pressure()
        engine_cpu_before = cpu()['engine']
        mark = time.monotonic()
        time.sleep(1 if quiet else .1)
        after = pressure()
        elapsed = time.monotonic() - mark
        state = get('client-lifecycle')
        stalls = {k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}
        engine_cpu_rate = (cpu()['engine'] - engine_cpu_before) / elapsed
        admitted = not state.get('sessions') and state['active_requests'] == 0 and (not quiet or (stalls['host.io.some'] < .05 and stalls['engine.io.some'] < .01 and stalls['host.cpu.some'] < .10 and engine_cpu_rate < .10))
        with (root / 'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label, admitted=admitted, stall_fraction=stalls, engine_cpu_rate=engine_cpu_rate, seconds=time.monotonic() - started)) + '\n')
        if admitted:
            return
        assert time.monotonic() - started < 90, 'admission timeout; preserve all completed observations'


def unix(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def nondeferred_overlaps(state, started, ended):
    return [event for event in state['events'] if not event['deferred'] and unix(event['start']) < ended and unix(event['end']) > started]


def profile_start():
    get('wcprof/enabled', b'on')
    with urllib.request.urlopen(debug + 'wcprof/dump', timeout=20) as response:
        while response.read(1048576):
            pass


def profile_end(label):
    get('wcprof/enabled', b'off')
    with urllib.request.urlopen(debug + 'wcprof/dump', timeout=20) as response:
        (root / (label + '.ndjson')).write_bytes(response.read())
    with (root / (label + '.ndjson')).open() as stream:
        header = json.loads(next(stream))
    assert not header['dropped_events'] and not header.get('open_ops'), label


from concurrent.futures import ThreadPoolExecutor
import gzip

rows=[]
def engine_profile(label):
    started=time.time()
    with urllib.request.urlopen(debug+'pprof/profile?seconds=5',timeout=15) as response:
        (root/(label+'-engine.cpu.pprof')).write_bytes(response.read())
    return {'started':started,'ended':time.time()}
try:
    config.write_text(re.sub(r'source = "[^"]+"','source = "'+str(module)+'"',original_config,count=1))
    assert not get('wcprof/enabled')['global_enabled']
    assert not get('snapshot-collection')['deferred']
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    mode('direct-span-protobuf',False);mode('snapshot-completions',False)
    mode('containerd-root-dedup',False);source_mode(True)
    (root/'metadata.json').write_text(json.dumps(dict(engine=json.loads((base/'containerd-root-dedup-single-lookup-engine/identity.json').read_text()),module='f73c5614a89968afa6f6000328e96ea33745fd93',command='check rust:packages/check',telemetry_enabled=True,compiler_and_engine_warm=True,fresh_processes=True,source_snapshot_seeds=True,natural_collection=True,forced_go_gc=False,scope='Diagnostic only: engine and CLI CPU profiles, CLI runtime trace, wcprof and goroutine captures; timings are not benchmark results.'),indent=2)+'\n')
    with ThreadPoolExecutor(max_workers=1) as pool:
        for index in range(args.pairs):
            label=str(index)
            path=source/'leaf_1023/src/lib.rs'
            text,count=re.subn(r'pub const EDIT: u64 = \d+;','pub const EDIT: u64 = '+str(secrets.randbits(48))+';',path.read_text());assert count==1;path.write_text(text)
            idle(label)
            profile_start()
            before_heap=heap();before_cpu=cpu();before_pressure=pressure()
            future=pool.submit(engine_profile,label)
            run_env=dict(env,CPUPROFILE=str(root/(label+'-cli.cpu.pprof')))
            started=time.monotonic();unix_started=time.time();captures=[]
            with (root/(label+'.log')).open('w') as output:
                process=subprocess.Popen([str(cli),'check','rust:packages/check'],cwd=source,env=run_env,stdout=output,stderr=subprocess.STDOUT)
                offsets=iter([.25,.6]);next_capture=next(offsets)
                while process.poll() is None:
                    elapsed=time.monotonic()-started
                    if elapsed>=next_capture:
                        tick=time.monotonic()
                        with urllib.request.urlopen(debug+'pprof/goroutine?debug=2',timeout=10) as response:data=response.read()
                        with gzip.open(root/(label+'-stack-'+str(len(captures))+'.txt.gz'),'wb') as output:output.write(data)
                        captures.append(dict(offset=elapsed,capture_seconds=time.monotonic()-tick,bytes=len(data)))
                        next_capture=next(offsets,float('inf'))
                    time.sleep(.01)
                process.wait()
            seconds=time.monotonic()-started;unix_ended=time.time()
            after_cpu=cpu();after_pressure=pressure();after_heap=heap()
            assert process.returncode==0 and 'passed' in (root/(label+'.log')).read_text(),label
            profile_end(label)
            window=future.result()
            assert (root/(label+'-cli.cpu.pprof')).stat().st_size>0
            assert (root/(label+'-cli.cpu.pprof.trace')).stat().st_size>0
            state=get('snapshot-collection')
            rows.append(dict(label=label,diagnostic_command_seconds=seconds,command_unix_start=unix_started,command_unix_end=unix_ended,engine_cpu_window=window,captures=captures,heap_delta={k:after_heap[k]-before_heap[k] for k in before_heap},cpu_delta={k:after_cpu[k]-before_cpu[k] for k in groups},collection_overlaps=nondeferred_overlaps(state,unix_started,unix_ended),stall_fraction={k:(after_pressure[k]-before_pressure[k])/(seconds*1e6) for k in before_pressure}))
            (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
            print('PASS capture',label,'diagnostic seconds',round(seconds,3),'engine CPU',round(rows[-1]['cpu_delta']['engine'],3),'Go GC',rows[-1]['heap_delta']['NumGC'],'collection overlaps',len(rows[-1]['collection_overlaps']),flush=True)
finally:
    config.write_text(original_config)
    get('wcprof/enabled',b'off')
    source_mode(False)
    mode('batch-metadata',False);mode('attribute-array-decode',False);mode('containerd-root-dedup',False)
