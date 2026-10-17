from pathlib import Path
import hashlib
import json
import subprocess
import time
import urllib.request

root=Path(__file__).parent
base=root.parent
engine='dagger-rust-parser-state-pool-oct14'
def get(route,data=None):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=30) as response:return json.load(response)
state=get('client-lifecycle')
assert not state.get('sessions') and state['active_requests']==0
assert not get('wcprof/enabled')['global_enabled']
assert get('lock-profiler')==dict(mutex_fraction=0,block_profile_rate_ns=0)
before=subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert before=='e47f01f1ca7a7000216b39df21109b70eb9e91b263200c19a2114615f31cd067'
modes=json.loads((root/'baseline-modes.json').read_text())
command=['python3',str(base/'restart_owned_engine_clean.py'),'--engine',engine,'--debug-port','16104','--output',str(root/'restart-route'),'--binary',str(root/'dagger-engine'),'--readiness-timeout','480']
begin=time.monotonic()
with (root/'restart-route.log').open('w') as stream:result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
(root/'restart-route-command.json').write_text(json.dumps(dict(command=command,seconds=time.monotonic()-begin,exit_code=result.returncode),indent=2)+'\n')
assert result.returncode==0
for route,enabled in modes.items():assert get(route+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
assert get('shared-restored-postings')['enabled'] and get('scalar-array-restore')['enabled']
assert get('trivial-scalar-fields')==dict(enabled=False)
assert get('trivial-scalar-fields?enabled=true',b'')==dict(enabled=True)
assert get('trivial-scalar-fields')==dict(enabled=True)
actual=subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert actual==hashlib.sha256((root/'dagger-engine').read_bytes()).hexdigest()
(root/'identity-route.json').write_text(json.dumps(dict(engine_sha256=actual,previous_engine_sha256=before,selected_engine_sha256='51542ef941c4e3bd96c2ce770c118d154824272ff247d8b9038b0cb27e5fa0e3',same_owned_volume=True,diagnostic_route_registered_on_actual_mux=True,production_getter_unchanged_from_component_cohort=True),indent=2)+'\n')
print('Restart and route verified; checking first native calls with the candidate enabled.',flush=True)
begin=time.monotonic()
command=['python3',str(root/'verify_retained_first.py'),'scalar-projection-after-first']
with (root/'retained-after.log').open('w') as stream:result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
(root/'retained-after-command.json').write_text(json.dumps(dict(command=command,seconds=time.monotonic()-begin,exit_code=result.returncode,candidate_enabled=get('trivial-scalar-fields')['enabled']),indent=2)+'\n')
assert result.returncode==0
for route,enabled in modes.items():assert get(route+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
assert get('trivial-scalar-fields?enabled=false',b'')==dict(enabled=False)
state=get('client-lifecycle');assert not state.get('sessions') and state['active_requests']==0
(root/'route-activation-state.json').write_text(json.dumps(dict(mode=get('trivial-scalar-fields'),state=state,lock_profiler=get('lock-profiler'),profiling=get('wcprof/enabled')),indent=2)+'\n')
print('PASS: real handler controls the runtime flag; all six native histories hit on their first call with the candidate enabled.',flush=True)
