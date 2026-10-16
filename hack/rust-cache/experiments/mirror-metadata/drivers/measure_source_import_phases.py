from pathlib import Path
import argparse
import gzip
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--runs', type=int, default=10)
parser.add_argument('--profile', action='store_true')
parser.add_argument('--mirror-policy', choices=['before','after','alternate'])
args = parser.parse_args()
args.output.mkdir(exist_ok=False)
base = Path('/tmp/rust-cache-sipsma-review')
source = Path('/tmp/rust-native-config-entry-1026-before')
raw = Path('/tmp/rust-cache-oct13-filter/local-receiver/telemetry.jsonl')
debug = 'http://127.0.0.1:16104/debug/'
engine = 'dagger-rust-parser-state-pool-oct14'

def get(route, data=None):
    with urllib.request.urlopen(urllib.request.Request(debug + route, data=data), timeout=30) as response:
        return json.load(response)

def mode(route, enabled):
    assert get(route + '?enabled=' + str(enabled).lower(), b'')['enabled'] == enabled

def seed_mode(enabled):
    subprocess.run(['docker', 'exec', '-i', engine, 'sh', '-c', 'cat > /tmp/filesync-snapshot-seeds-mode'], input=b'on\n' if enabled else b'off\n', check=True, stdout=subprocess.DEVNULL)

def engine_profile(n):
    with urllib.request.urlopen(debug+'pprof/profile?seconds=5', timeout=15) as response:
        (args.output/f'{n}-engine.cpu.pprof').write_bytes(response.read())

def wcprof_start():
    get('wcprof/enabled', b'on')
    with urllib.request.urlopen(debug+'wcprof/dump',timeout=30) as response:
        while response.read(1048576): pass

def wcprof_end(n):
    get('wcprof/enabled', b'off')
    chunks=[]
    for _ in range(100):
        with urllib.request.urlopen(debug+'wcprof/dump',timeout=30) as response: raw=response.read()
        lines=raw.splitlines(); header=json.loads(lines[0]);chunks.append((header,lines[1:]))
        assert not header['dropped_events']
        if not header.get('open_ops'):break
        time.sleep(.1)
    else:raise AssertionError('wcprof operations did not complete')
    final=dict(chunks[-1][0]); events=[]
    for header,lines in chunks:
        assert final['strings'][:len(header['strings'])]==header['strings'];events.extend(lines)
    final['event_count']=len(events)
    with (args.output/f'{n}-wcprof.ndjson').open('wb') as stream:
        stream.write(json.dumps(final).encode()+b'\n')
        for line in events:stream.write(line+b'\n')

def pressure():
    return {kind + '.' + line.split()[0]: int(line.split('total=')[1]) for kind in ['cpu', 'io', 'memory'] for line in Path('/proc/pressure', kind).read_text().splitlines()}

def idle(label):
    started = time.monotonic()
    while True:
        before = pressure(); mark = time.monotonic(); time.sleep(1)
        after = pressure(); seconds = time.monotonic() - mark
        stalls = {k: (after[k] - before[k]) / seconds / 1e6 for k in before}
        state = get('client-lifecycle')
        admitted = not state['sessions'] and state['active_requests'] == 0 and stalls['io.some'] < .05 and stalls['cpu.some'] < .10
        with (args.output / 'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label, admitted=admitted, stall_fraction=stalls)) + '\n')
        if admitted: return
        assert time.monotonic() - started < 90, 'admission timeout'

env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276', RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'), RUST_CACHE_BENCH_COLLECTOR='http://' + raw.with_name('address.txt').read_text().strip() + ':43183')
rows = []
try:
    assert get('dimension-key-fields')['enabled']
    assert not get('parallel-fingerprint')['enabled']
    assert not get('wcprof/enabled')['global_enabled']
    assert not get('snapshot-collection')['deferred']
    assert '/tmp/dagger-rust-native-discovery-current' in (source/'dagger.toml').read_text()
    mode('batch-metadata', True); mode('attribute-array-decode', True); seed_mode(True)
    (args.output/'metadata.json').write_text(json.dumps(dict(engine_sha256=subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0], module_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd='/tmp/dagger-rust-native-discovery-current',text=True).strip(), source=str(source), telemetry_enabled=True, fresh_edit_each_run=True, selected_serial_fingerprint=True, forced_gc=False, phase_timings_are_diagnostic=True, source_snapshot_seeds=True),indent=2)+'\n')
    for n in range(args.runs):
        filename = source/'leaf_1023/src/lib.rs'
        edit = secrets.randbits(48)
        text, count = re.subn(r'pub const EDIT: u64 = \d+;', f'pub const EDIT: u64 = {edit};', filename.read_text())
        assert count == 1; filename.write_text(text)
        idle(str(n))
        policy=args.mirror_policy
        if policy=='alternate':policy=['before','after','after','before'][n%4]
        if policy:mode('mirror-metadata',policy=='after')
        run_env=dict(env)
        if args.profile:
            wcprof_start()
            pool=ThreadPoolExecutor(max_workers=1); future=pool.submit(engine_profile,n)
            run_env['CPUPROFILE']=str(args.output/f'{n}-cli.cpu.pprof')
            time.sleep(.15)
        offset = raw.stat().st_size
        before = pressure(); begin_ns = time.time_ns(); start = time.monotonic()
        with (args.output/f'{n}.log').open('w') as output:
            result = subprocess.run(['python3',str(base/'local_cli_collector.py'),'check','rust:packages/check'],cwd=source,env=run_env,stdout=output,stderr=subprocess.STDOUT)
        seconds = time.monotonic()-start; end_ns = time.time_ns(); after = pressure()
        assert result.returncode == 0, (n,result.returncode)
        assert 'passed' in (args.output/f'{n}.log').read_text(), n
        end = raw.stat().st_size
        assert 0 < end-offset < 128*1024*1024, ('bounded telemetry window exceeded',end-offset)
        spans = {}; live = 0
        with raw.open('rb') as stream:
            stream.seek(offset); capture = stream.read(end-offset)
        for line in capture.splitlines():
            record = json.loads(line)
            if record.get('kind') != 'span': continue
            if not (0 < record.get('startNs',0) <= record.get('endNs',0) <= end_ns+5_000_000_000):
                live += 1; continue
            spans[(record['traceId'],record['spanId'])] = record
        compact = [{k:r[k] for k in ('traceId','spanId','parentId','name','scope','startNs','endNs','status','statusMsg') if k in r} for r in spans.values()]
        with gzip.open(args.output/f'{n}-completed-spans.json.gz','wt') as stream: json.dump(compact,stream)
        selected = [r for r in spans.values() if 'Host.directory' in r['name'] or 'filesync' in r.get('scope','') or r['name']=='copy' or str(source) in r['name']]
        with gzip.open(args.output/f'{n}-import-spans.json.gz','wt') as stream: json.dump(selected,stream)
        def short(r): return dict(name=r['name'][:160],scope=r.get('scope'),spanId=r['spanId'],parentId=r.get('parentId'),milliseconds=(r['endNs']-r['startNs'])/1e6)
        row = dict(run=n, mirror_policy=policy,source_edit_value=edit, command_seconds=seconds, command_start_ns=begin_ns, command_end_ns=end_ns, telemetry_start=offset,telemetry_end=end,telemetry_bytes=end-offset,telemetry_sha256=hashlib.sha256(capture).hexdigest(),completed_spans=len(spans),unfinished_updates=live,selected=[short(r) for r in selected],stall_fraction={k:(after[k]-before[k])/seconds*1e-6 for k in before},snapshot_collection=get('snapshot-collection'))
        rows.append(row); (args.output/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps(dict(run=n,seconds=seconds,telemetry_mb=(end-offset)/1e6,selected=row['selected'])),flush=True)
        if args.profile:
            wcprof_end(n);future.result();pool.shutdown()
finally:
    if args.profile:get('wcprof/enabled',b'off')
    if args.mirror_policy:mode('mirror-metadata',False)
    seed_mode(False); mode('batch-metadata',False); mode('attribute-array-decode',False)
