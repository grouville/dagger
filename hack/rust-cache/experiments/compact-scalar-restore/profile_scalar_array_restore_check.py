from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base/'scalar-array-restore-current-check-profile'
root.mkdir(exist_ok=False)
modules = {'before':'/tmp/dagger-rust-local-package-fingerprint', 'after':'/tmp/dagger-rust-local-package-fingerprint'}
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
           RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
configs = {}
results = []

def debug(route, data=None, timeout=30):
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=timeout)

def mode(name,value):
    with debug(name+'?enabled='+str(value).lower(),b'') as response:
        assert json.load(response)['enabled']==value

def dump(label):
    with debug('wcprof/dump') as response, (root/(label+'.ndjson')).open('wb') as output:
        while chunk:=response.read(1048576):output.write(chunk)

def capture_cpu(label):
    with debug('pprof/profile?seconds=10',timeout=20) as response:
        (root/(label+'-engine.pprof')).write_bytes(response.read())

def run(label,size,history,variant,cpu,listing):
    source = Path(f'/tmp/rust-native-config-entry-{size}-{history}')
    config = source/'dagger.toml'
    if config not in configs:configs[config]=config.read_text()
    updated,count=re.subn(r'source = "[^"]+"',f'source = "{modules[variant]}"',configs[config],count=1)
    assert count==1
    config.write_text(updated)
    filename=source/('leaf_0127/src/lib.rs' if size=='130' else 'leaf_1023/src/lib.rs')
    updated,count=re.subn(r'pub const EDIT: u64 = \d+;',f'pub const EDIT: u64 = {secrets.randbits(48)};',filename.read_text())
    assert count==1
    filename.write_text(updated)
    while True:
        with debug('client-lifecycle') as response:state=json.load(response)
        if not state.get('sessions') and not state['active_requests']:break
        time.sleep(.1)
    time.sleep(1)
    mode('direct-span-protobuf', variant == 'after')
    with debug('batch-metadata?enabled=true&record=true',b''):pass
    with debug('wcprof/enabled',b'on'):pass
    with debug('wcprof/dump') as response:
        while response.read(1048576):pass
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(capture_cpu,label) if cpu else None
        if cpu:time.sleep(.05)
        start=time.monotonic()
        with (root/(label+'.log')).open('w') as output:
            command=['python3',str(base/'local_cli_collector.py'),'check']+(['--list','--all','rust:packages/check'] if listing else ['rust:packages/check'])
            process=subprocess.run(command,cwd=source,env=env,stdout=output,stderr=subprocess.STDOUT)
        seconds=time.monotonic()-start
        with debug('wcprof/enabled',b'off'):pass
        if future:future.result()
    dump(label)
    assert process.returncode==0,label
    listed=re.findall(r'^rust\s+(\S+)\s+check$',(root/(label+'.log')).read_text(),re.M)
    expected={'app','shared'}|{f'leaf_{i:04d}' for i in range(1024)}
    if listing:
        assert len(listed)==1026 and set(listed)==expected,(label,len(listed))
    else:
        assert 'passed' in (root/(label+'.log')).read_text(),label
    with debug('batch-metadata') as response:metadata=json.load(response)
    with (root/(label+'.ndjson')).open() as stream:
        header=json.loads(next(stream));strings=header['strings'];ops=list(map(json.loads,stream))
    assert not header['dropped_events'] and not header.get('open_ops'),label
    selected=[]
    for op in ops:
        cls=strings[op.get('c',0)]
        if op.get('e')=='op' and op.get('k') in ['call_exec','exec','exec_phase','internal'] and any(term in cls for term in ['Rust.packages','Check.sync','treeFingerprint','Host.directory','dang.decodeSchema','dang.parse','dang.infer','dang.invoke','ModuleSource.asModule','withExec.prepareMounts']):
            selected.append(dict(cls=cls,kind=op['k'],milliseconds=(op['d']-op['s'])/1e6,id=op['id']))
    result=dict(label=label,diagnostic_only=True,seconds=seconds,size=size,history=history,module=modules[variant],engine_cpu_profile=cpu,listing=listing,telemetry_conversions=metadata,events=header['event_count'],dropped=header['dropped_events'],open=header.get('open_ops',0),selected=selected)
    results.append(result)
    (root/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    print('PASS',label,round(seconds,3),'diagnostic seconds',flush=True)

try:
    mode('batch-metadata',True)
    mode('attribute-array-decode',True)
    mode('snapshot-completions',False)
    with debug('scalar-array-restore') as response:assert json.load(response)['enabled']
    run('1026-compact-check','1026','before','before',True,False)
finally:
    with debug('wcprof/enabled',b'off'):pass
    mode('direct-span-protobuf',False)
    mode('batch-metadata',False)
    mode('attribute-array-decode',False)
    for config,original in configs.items():config.write_text(original)
