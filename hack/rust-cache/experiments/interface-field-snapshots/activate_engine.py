from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
import urllib.request

root=Path(__file__).parent;base=root.parent
phases=[]
def get(route,data=None):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as r:return json.load(r)
def mode(name,enabled):assert get(name+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
def run(label,command):
    start=time.time()
    with (root/(label+'.log')).open('w') as out:result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    phases.append(dict(label=label,exit_code=result.returncode,unix_start=start,unix_end=time.time(),command=command))
    (root/'activation.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(label,result.returncode,flush=True);assert result.returncode==0,label
state=get('client-lifecycle');assert not state.get('sessions') and state['active_requests']==0
old=subprocess.check_output(['docker','exec','dagger-rust-parser-state-pool-oct14','sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert old=='2a32d997c29cf0f2a6bcc6fe6564e1f7a7729c2d158773eab9a35cb5d594cc84'
run('retained-before',['python3',str(base/'check_native_discovery_current_reuse.py'),'interface-snapshots-before'])
run('restart',['python3',str(base/'restart_owned_engine_clean.py'),'--engine','dagger-rust-parser-state-pool-oct14','--debug-port','16104','--output',str(root/'restart'),'--binary',str(root/'dagger-engine'),'--readiness-timeout','300'])
mode('dimension-key-fields',True);mode('artifact-metadata-fields',True)
assert not get('interface-field-snapshots')['enabled']
new=subprocess.check_output(['docker','exec','dagger-rust-parser-state-pool-oct14','sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert new==hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest()
(root/'identity.json').write_text(json.dumps(dict(engine_sha256=new,base_engine_sha256=old,source_base='19eda924854e7f22582f3a7430272aa729cbeb5f',diagnostic_route='/debug/interface-field-snapshots',default_enabled=False),indent=2)+'\n')
try:
    mode('interface-field-snapshots',True)
    run('retained-after',['python3',str(base/'check_native_discovery_current_reuse.py'),'interface-snapshots-after'])
finally:mode('interface-field-snapshots',False)
print('Clean restart, selected getters restored, six native histories retained; candidate OFF.',flush=True)
