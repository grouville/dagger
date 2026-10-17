from pathlib import Path
import json,subprocess,time,urllib.request
family=Path(__file__).parent
root=family/'allocation-analysis'
root.mkdir(exist_ok=False)
url='http://127.0.0.1:16104/debug/'
def get(route):
 with urllib.request.urlopen(url+route,timeout=40) as response:return response.read()
state=json.loads(get('client-lifecycle'))
assert not state.get('sessions') and state['active_requests']==0
assert json.loads(get('lock-profiler'))==dict(mutex_fraction=0,block_profile_rate_ns=0)
assert not json.loads(get('parallel-client-admission'))['enabled']
(root/'engine-allocs.pprof').write_bytes(get('pprof/allocs'))
(root/'vars-after-cohort.json').write_bytes(get('vars'))
rows=json.loads((family/'full-command-paired/samples.json').read_text())
metadata=dict(scope='Cumulative engine allocation samples from this process after startup through the complete ten-command cohort, including pre-cohort Rust retained-history checks. Both admission modes are included; this is attribution, not an A/B allocation comparison. No forced GC. Heap samples can lag live allocations by up to two GC cycles.',
 cohort_commands=len(rows),cohort_total_allocated_bytes=sum(r['heap_delta']['TotalAlloc'] for r in rows),
 profile_baseline=str(family/'startup-heap.pprof'),feature_enabled=False)
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
commands=[]
for metric in ['alloc_space','alloc_objects']:
 for cumulative in [False,True]:
  name=metric+('-cumulative' if cumulative else '-flat')+'.txt'
  cmd=[go,'tool','pprof','-top','-nodecount=65','-sample_index='+metric,'-base',str(family/'startup-heap.pprof')]
  if cumulative:cmd.append('-cum')
  cmd.extend([str(family/'dagger-engine'),str(root/'engine-allocs.pprof')])
  with (root/name).open('w') as out:subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
  commands.append(dict(output=name,command=cmd))
(root/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
print(json.dumps(metadata,indent=2))
