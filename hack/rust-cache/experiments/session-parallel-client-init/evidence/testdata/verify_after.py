from pathlib import Path
import hashlib,json,subprocess,urllib.request
root=Path(__file__).parent
base=root.parent
url='http://127.0.0.1:16104/debug/'
def get(route,data=None):
 with urllib.request.urlopen(urllib.request.Request(url+route,data=data),timeout=30) as response:return json.load(response)
assert not get('parallel-client-admission')['enabled']
try:
 assert get('parallel-client-admission?enabled=true',b'')['enabled']
 cmd=['python3',str(base/'interface-field-snapshots/verify_retained.py'),'session-parallel-client-init-enabled']
 with (root/'retained-enabled.log').open('w') as output:
  result=subprocess.run(cmd,stdout=output,stderr=subprocess.STDOUT)
 assert result.returncode==0,'native Rust retained-history check with candidate enabled'
finally:
 assert not get('parallel-client-admission?enabled=false',b'')['enabled']
routes=['parallel-client-admission','single-toml-parse','lock-profiler','span-lookup-fanout','span-resource-batches','otel-evicted-queue','lazy-type-maps','callback-caller-reuse','telemetry-flush-coalescing','interface-candidate-pruning','interface-field-snapshots','collection-expansion-values','collection-expansion-limit','batch-metadata','attribute-array-decode','reusable-declarations','snapshot-collection','wcprof/enabled','client-lifecycle']
state={r:get(r) for r in routes}
(root/'state-after.json').write_text(json.dumps(state,indent=2)+'\n')
assert state['lock-profiler']==dict(mutex_fraction=0,block_profile_rate_ns=0)
assert state['span-lookup-fanout']['enabled']
for route in ['parallel-client-admission','single-toml-parse','span-resource-batches','otel-evicted-queue','lazy-type-maps','callback-caller-reuse','telemetry-flush-coalescing','interface-candidate-pruning','interface-field-snapshots','collection-expansion-values','batch-metadata','attribute-array-decode','reusable-declarations']:
 assert not state[route]['enabled'],route
assert not state['snapshot-collection']['deferred']
assert not state['wcprof/enabled']['global_enabled']
assert state['collection-expansion-limit']['limit']==0
assert not state['client-lifecycle'].get('sessions') and state['client-lifecycle']['active_requests']==0
print('PASS: six native Rust histories reuse every action with the candidate enabled; all unselected modes and profilers restored off.')
