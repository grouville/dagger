from pathlib import Path
import hashlib
import json
import subprocess
import time
import urllib.request

root=Path(__file__).parent
base=Path('/tmp/rust-cache-sipsma-review')
engine='dagger-rust-parser-state-pool-oct14'
def get(route,data=None):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as r:return json.load(r)
phases=[]
def run(label,command):
    started=time.time()
    with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    phases.append(dict(label=label,command=command,exit_code=r.returncode,unix_start=started,unix_end=time.time()))
    (root/'activation.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(label,r.returncode,flush=True)
    assert r.returncode==0,label

state=get('client-lifecycle')
assert not state.get('sessions') and state['active_requests']==0
old=subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert old=='bc84e90ae997a41441eb74ef49d689c6982ffcd18467dba6573562870f5841bb',old
routes=['dimension-key-fields','artifact-metadata-fields','interface-field-snapshots','layercopy-known-dirs','span-lookup-fanout','batch-metadata','attribute-array-decode','direct-span-protobuf','collection-expansion-values']
modes={route:get(route)['enabled'] for route in routes}
assert not get('wcprof/enabled')['global_enabled']
assert not get('snapshot-collection')['deferred']
assert get('collection-expansion-limit')['limit']==0
(root/'baseline-modes.json').write_text(json.dumps(modes,indent=2)+'\n')
run('retained-before',['python3',str(base/'interface-field-snapshots/verify_retained.py'),'flush-coalescing-before'])
run('restart',['python3',str(base/'restart_owned_engine_clean.py'),'--engine',engine,'--debug-port','16104','--output',str(root/'restart'),'--binary',str(root/'dagger-engine'),'--readiness-timeout','480'])
for route,enabled in modes.items():assert get(route+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
assert get('collection-expansion-limit')['limit']==0
assert not get('gc-metadata-read-ahead')['enabled']
new=subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert new==hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest()
(root/'identity.json').write_text(json.dumps(dict(engine_sha256=new,previous_engine_sha256=old,source_base='19eda924854e7f22582f3a7430272aa729cbeb5f',diagnostic_route='/debug/telemetry-flush-coalescing',default_enabled=False,source='Per-session telemetry flush coverage barrier. All signals and per-caller flush guarantees retained; overlapping flushes coalesced.'),indent=2)+'\n')
try:
    assert not get('reusable-declarations')['enabled']
    assert not get('known-input-ids')['enabled']
    assert not get('telemetry-flush-coalescing')['enabled']
    run('retained-after',['python3',str(base/'interface-field-snapshots/verify_retained.py'),'flush-coalescing-after'])
finally:
    assert not get('reusable-declarations?enabled=false',b'')['enabled']
    assert not get('gc-metadata-read-ahead')['enabled']
    for route,enabled in modes.items():assert get(route+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
scope=json.loads((root/'scope.json').read_text());scope.update(installed=True,engine_sha256=new)
(root/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
print('Owned engine replaced gracefully; native histories retained; telemetry flush coalescing left off.',flush=True)
