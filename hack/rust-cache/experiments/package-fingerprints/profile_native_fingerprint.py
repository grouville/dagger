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
root = base/'native-fingerprint-profiles'
root.mkdir(exist_ok=False)
modules = {'original':'/tmp/dagger-rust-metadata-toolchain',
           'shell':'/tmp/dagger-rust-package-metadata-cache',
           'native':'/tmp/dagger-rust-native-package-fingerprint'}
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
    with debug('pprof/profile?seconds=3',timeout=10) as response:
        (root/(label+'-engine.pprof')).write_bytes(response.read())

def run(label,size,history,variant,cpu):
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
    with debug('wcprof/enabled',b'on'):pass
    with debug('wcprof/dump') as response:
        while response.read(1048576):pass
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(capture_cpu,label) if cpu else None
        if cpu:time.sleep(.05)
        start=time.monotonic()
        with (root/(label+'.log')).open('w') as output:
            process=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check','rust:check' if size=='130' else 'rust:packages/check'],cwd=source,env=env,stdout=output,stderr=subprocess.STDOUT)
        seconds=time.monotonic()-start
        with debug('wcprof/enabled',b'off'):pass
        if future:future.result()
    dump(label)
    assert process.returncode==0 and 'passed' in (root/(label+'.log')).read_text(),label
    with (root/(label+'.ndjson')).open() as stream:
        header=json.loads(next(stream));strings=header['strings'];ops=list(map(json.loads,stream))
    assert not header['dropped_events'] and not header.get('open_ops'),label
    selected=[]
    for op in ops:
        cls=strings[op.get('c',0)]
        if op.get('e')=='op' and op.get('k') in ['call_exec','exec','exec_phase','internal'] and any(term in cls for term in ['Rust.packages','Check.sync','treeFingerprint','Host.directory','dang.decodeSchema','dang.parse','dang.infer','dang.invoke','ModuleSource.asModule','withExec.prepareMounts']):
            selected.append(dict(cls=cls,kind=op['k'],milliseconds=(op['d']-op['s'])/1e6,id=op['id']))
    result=dict(label=label,diagnostic_only=True,seconds=seconds,size=size,history=history,module=modules[variant],engine_cpu_profile=cpu,events=header['event_count'],dropped=header['dropped_events'],open=header.get('open_ops',0),selected=selected)
    results.append(result)
    (root/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    print('PASS',label,round(seconds,3),'diagnostic seconds',flush=True)

try:
    mode('batch-metadata',True)
    mode('attribute-array-decode',True)
    mode('snapshot-completions',False)
    for history,variants in [('before',['shell','native']),('after',['native','shell'])]:
        for variant in variants:run(f'1026-{history}-{variant}','1026',history,variant,True)
    for round_,variants in [(0,['original','shell','native']),(1,['native','shell','original'])]:
        for variant in variants:run(f'130-control-{round_}-{variant}','130','before',variant,False)
finally:
    with debug('wcprof/enabled',b'off'):pass
    mode('batch-metadata',False)
    mode('attribute-array-decode',False)
    for config,original in configs.items():config.write_text(original)
