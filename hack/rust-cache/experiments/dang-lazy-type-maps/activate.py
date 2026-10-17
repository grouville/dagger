from pathlib import Path
import hashlib,json,subprocess,time,urllib.request,datetime
root=Path(__file__).parent;base=root.parent
engine='dagger-rust-parser-state-pool-oct14'
def get(route,data=None):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as r:return json.load(r)
phases=[]
def run(label,command):
    started=time.time()
    with (root/(label+'.log')).open('w') as out:p=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    phases.append(dict(label=label,command=command,exit_code=p.returncode,unix_start=started,unix_end=time.time()))
    (root/'activation.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(label,p.returncode,flush=True);assert p.returncode==0,label
state=get('client-lifecycle');assert not state.get('sessions') and state['active_requests']==0
old=subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert old=='21b62c6cfe77dd2787c001097a0a28a003e65ec72496555ae70dcb060d2db111',old
routes=['callback-caller-reuse','telemetry-flush-coalescing','dimension-key-fields','artifact-metadata-fields','interface-field-snapshots','interface-candidate-pruning','layercopy-known-dirs','span-lookup-fanout','batch-metadata','attribute-array-decode','direct-span-protobuf','collection-expansion-values']
modes={r:get(r)['enabled'] for r in routes}
assert not modes['interface-candidate-pruning'] and not modes['interface-field-snapshots']
assert not get('wcprof/enabled')['global_enabled'] and not get('snapshot-collection')['deferred']
assert get('scalar-array-restore')['enabled']
(root/'baseline-modes.json').write_text(json.dumps(modes,indent=2)+'\n')
(root/'vars-before.json').write_text(json.dumps(get('vars')['memstats'],indent=2)+'\n')
run('retained-before',['python3',str(base/'interface-field-snapshots/verify_retained.py'),'lazy-type-maps-before'])
subprocess.run(['docker','exec','-i',engine,'sh','-c','cat > /tmp/shared-restored-postings-mode'],input=b'on\n',check=True)
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
run('restart',['python3',str(base/'restart_owned_engine_clean.py'),'--engine',engine,'--debug-port','16104','--output',str(root/'restart'),'--binary',str(root/'dagger-engine'),'--readiness-timeout','480'])
logs=subprocess.check_output(['docker','logs','--since',started,engine],stderr=subprocess.STDOUT,text=True)
(root/'startup.log').write_text(logs)
for bad in ['wiping and cold-starting','persistence import failed','panic:','fatal error:']:assert bad not in logs,bad
for r,v in modes.items():assert get(r+'?enabled='+str(v).lower(),b'')['enabled']==v
assert get('shared-restored-postings')['enabled'] and get('scalar-array-restore')['enabled']
assert not get('gc-metadata-read-ahead')['enabled'] and get('collection-expansion-limit')['limit']==0
new=subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert new==hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest()
(root/'identity.json').write_text(json.dumps(dict(engine_sha256=new,previous_engine_sha256=old,source_base='19eda924854e7f22582f3a7430272aa729cbeb5f',standalone_base='ff0b029a4d270a651b9a8c7286babc79089066e4',same_owned_volume=True,shared_restored_postings=True,interface_experiments=False),indent=2)+'\n')
(root/'vars-after-startup.json').write_text(json.dumps(get('vars')['memstats'],indent=2)+'\n')
with urllib.request.urlopen('http://127.0.0.1:16104/debug/pprof/heap',timeout=30) as r:(root/'startup-heap.pprof').write_bytes(r.read())
run('retained-after',['python3',str(base/'interface-field-snapshots/verify_retained.py'),'lazy-type-maps-after'])
for r,v in modes.items():assert get(r+'?enabled='+str(v).lower(),b'')['enabled']==v
assert not get('lazy-type-maps')['enabled']
(root/'vars-after-retained.json').write_text(json.dumps(get('vars')['memstats'],indent=2)+'\n')
print('PASS: same cache preserved, six native Rust histories retained, both interface experiments off.',flush=True)
