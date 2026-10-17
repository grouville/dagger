from pathlib import Path
import gzip
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request

prefetch = '--prefetch-metadata' in sys.argv
if prefetch: sys.argv.remove('--prefetch-metadata')
protocol = Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
exec(protocol.read_text().split('fixtures = [f for f')[0])
cli = Path('/tmp/rust-cache-sipsma-review/glob-literal-prefix/dagger-after')
env['_EXPERIMENTAL_DAGGER_VERSION']='v1.0.0-beta.15'
env['CPUPROFILE']=str(root/'cli-cpu.pprof')
workspace = Path('/tmp/dagger-go-real-repository-main')
module = Path('/tmp/dagger-go-module-test-name-index')
source = workspace/'dagql/types.go'
original_source = source.read_bytes()
originals = {name: (workspace/name).read_bytes() if (workspace/name).exists() else None for name in ['dagger.toml', 'dagger.lock']}
routes = ['batch-metadata', 'attribute-array-decode', 'collection-expansion-values', 'reusable-declarations', 'known-input-ids', 'callback-caller-reuse', 'telemetry-flush-coalescing', 'interface-candidate-pruning']
flags = {r: get(r)['enabled'] for r in routes}
seed_path = '/tmp/filesync-snapshot-seeds-mode'
seed_mode = subprocess.check_output(['docker', 'exec', record['Id'], 'cat', seed_path])
engine_pid = next(int(line.split()[0]) for line in subprocess.check_output(['docker','top',record['Id'],'-eo','pid,comm'],text=True).splitlines()[1:] if line.split()[1] == 'dagger-engine')
def raw(route, timeout=30):
    with urllib.request.urlopen(debug+route, timeout=timeout) as r: return r.read()
def counters():
    result = {}
    for name in ['memory.stat','cpu.stat','io.stat','memory.events']:
        result[name] = (cgroup/name).read_text()
    fields = Path(f'/proc/{engine_pid}/stat').read_text().rsplit(')',1)[1].split()
    result['engine_minor_faults'] = int(fields[7])
    result['engine_major_faults'] = int(fields[9])
    result['memory_current'] = int((cgroup/'memory.current').read_text())
    result['pressure'] = pressure()
    return result

stop = threading.Event()
rows = []
errors = []
prefetches = []
seen_collectors = set()
def sample():
    next_heap = next_stack = 0
    while not stop.wait(1):
        offset = time.monotonic()-tick
        row = dict(seconds=offset, unix_time=time.time(), **counters())
        if offset >= next_heap:
            try:
                row['heap'] = heap()
                row['expansion'] = get('collection-expansion-limit')
                row['snapshot_collection'] = get('snapshot-collection')
            except Exception as error: row['debug_error'] = str(error)
            next_heap = offset+4
        if offset >= next_stack:
            try:
                data = raw('pprof/goroutine?debug=2', 15)
                (root/f'goroutines-{int(offset)}.txt.gz').write_bytes(gzip.compress(data,mtime=0))
                stacks = data.decode().split('\n\n')
                row['gc_stacks'] = [s for s in stacks if 'core/metadata.(*DB).GarbageCollect' in s]
                row['metadata_update_waiters'] = sum('core/metadata.(*DB).Update' in s and 'RWMutex' in s for s in stacks)
                row['bbolt_waiters'] = sum('go.etcd.io/bbolt.' in s and 'Mutex' in s for s in stacks)
                print(json.dumps(dict(seconds=round(offset,1), gc_active=bool(row['gc_stacks']), metadata_update_waiters=row['metadata_update_waiters'], major_faults=row['engine_major_faults'])),flush=True)
                for stack in row['gc_stacks']:
                    if not prefetch or '.scanRoots(' not in stack: continue
                    collector = stack.splitlines()[0].split()[1]
                    if collector in seen_collectors: continue
                    seen_collectors.add(collector)
                    begin = time.monotonic()
                    entry = dict(collector=collector,command_offset=begin-tick,unix_start=time.time(),before=counters())
                    command = ['docker','exec',record['Id'],'sh','-c','cat /var/lib/dagger/worker/containerdmeta.db > /dev/null']
                    run = subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=45)
                    entry.update(seconds=time.monotonic()-begin,unix_end=time.time(),exit_code=run.returncode,stderr=run.stderr,after=counters())
                    prefetches.append(entry)
                    (root/'prefetches.json').write_text(json.dumps(prefetches,indent=2)+'\n')
                    print(json.dumps(dict(prefetch_seconds=entry['seconds'],exit_code=run.returncode,collector=collector)),flush=True)
            except Exception as error: row['stack_error'] = str(error)
            next_stack = offset+10
        rows.append(row)
        (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')

def capture_cpu():
    for at in [5,25,45,90,135,180,240]:
        if stop.wait(max(0,at-(time.monotonic()-tick))): return
        started = time.time()
        try:
            data = raw('pprof/profile?seconds=5',20)
            (root/f'cpu-{at}.pprof').write_bytes(data)
            (root/f'cpu-{at}-window.json').write_text(json.dumps(dict(start=started,end=time.time(),offset=started-wall_tick))+'\n')
        except Exception as error: errors.append(dict(scope='cpu',at=at,error=str(error)))

assert not get('wcprof/enabled')['global_enabled']
assert not get('snapshot-collection')['deferred']
assert get('collection-expansion-limit')['limit'] == 0
idle('profile')
(root/'allocs-before.pprof').write_bytes(raw('pprof/allocs'))
before = counters()
gc_before = get('snapshot-collection')
metadata = dict(scope='Diagnostic complete Go listing with host glob prefix pruning, ordered parallel module/package discovery, guarded reuse of discovered module ownership and shared restored digest postings; interface experiments disabled; client admission phases instrumented; declaration reuse on and callback reuse, session flush coalescing and known-ID optimization off; CPU and allocation profiles plus wcprof. Not a clean latency benchmark.',
    command=[str(cli),'check','--module','go','--check','test','--list','--all'],
    engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],
    workspace_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=workspace,text=True).strip(),
    module_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=module,text=True).strip(),
    warm_engine=True,fresh_source_edit=True,telemetry=True,ordinary_gc=True,forced_gc=False,
    prefetch_diagnostic=prefetch,prefetch_scope='If enabled, read the metadata file sequentially once per observed natural root scan. Included inside the command interval. No writes or garbage-collection policy changes. This is a causal diagnostic, not an installed engine optimization.',
    flags=flags,counters_before=before,gc_before=gc_before,engine_pid=engine_pid)
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
threads=[]
cancelled=False
try:
    mode('batch-metadata',True); mode('attribute-array-decode',True)
    mode('collection-expansion-values',False)
    mode('reusable-declarations',True)
    mode('known-input-ids',False)
    mode('callback-caller-reuse',False)
    mode('telemetry-flush-coalescing',False)
    mode('interface-candidate-pruning',False)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=b'on\n',check=True)
    source.write_bytes(original_source+f'\n// Profile Go listing {time.time_ns()}\n'.encode())
    (workspace/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
    get('wcprof/enabled',b'on'); raw('wcprof/dump')
    tick=time.monotonic();wall_tick=time.time()
    threads=[threading.Thread(target=sample),threading.Thread(target=capture_cpu)]
    for thread in threads:thread.start()
    with (root/'command.stdout').open('w') as out,(root/'command.stderr').open('w') as err:
        process=subprocess.Popen(metadata['command'],cwd=workspace,env=env,stdout=out,stderr=err,start_new_session=True)
        try:code=process.wait(timeout=330)
        except subprocess.TimeoutExpired:
            cancelled=True;os.killpg(process.pid,signal.SIGINT);code=process.wait()
    elapsed=time.monotonic()-tick
finally:
    stop.set()
    for thread in threads:thread.join()
    get('wcprof/enabled',b'off')
    source.write_bytes(original_source)
    for name,original in originals.items():
        if original is None:(workspace/name).unlink(missing_ok=True)
        else:(workspace/name).write_bytes(original)
    for route,value in flags.items():mode(route,value)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=seed_mode,check=True)
(root/'allocs-after.pprof').write_bytes(raw('pprof/allocs'))
chunks=[]
started=time.monotonic()
while True:
    data=raw('wcprof/dump',45)
    (root/f'wcprof-{len(chunks)}.ndjson.gz').write_bytes(gzip.compress(data,mtime=0))
    lines=data.splitlines();header=json.loads(lines[0]);chunks.append((header,lines[1:]))
    if not header.get('open_ops'):break
    if time.monotonic()-started>100:
        errors.append(dict(scope='wcprof',error='Recorded operations still open after 100 seconds'));break
    time.sleep(1)
final=dict(chunks[-1][0]);events=[]
for header,lines in chunks:
    assert final['strings'][:len(header['strings'])]==header['strings']
    events.extend(lines)
final['event_count']=len(events)
(root/'wcprof-complete.ndjson').write_bytes((json.dumps(final)+'\n').encode()+b'\n'.join(events)+b'\n')
listed=[line for line in (root/'command.stdout').read_text().splitlines() if line.startswith('go ')]
expected=[line for line in (base/'collection-expansion-values/go-listing/0-before.stdout').read_text().splitlines() if line.startswith('go ')]
result=dict(seconds=elapsed,exit_code=code,cancelled=cancelled,listed_rows=len(listed),same_rows=listed==expected,
    counters_after=counters(),gc_after=get('snapshot-collection'),recorder=dict(events=len(events),dropped=final['dropped_events'],open=len(final.get('open_ops',[]))),errors=errors,
    restored_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),original_source_sha256=hashlib.sha256(original_source).hexdigest())
(root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['gc_after','counters_after']}),flush=True)
assert not cancelled and len(listed)==4398 and listed==expected
