"""Numeric, allowlisted projection of a local wcprof capture; no input strings."""
from pathlib import Path
from collections import Counter
import hashlib,json
ROOT=Path(__file__).resolve().parent
PATH=ROOT/'local-v1/10-checks-wcprof/run.wcprof.private'
with PATH.open() as f:
    header=json.loads(next(f)); events=[json.loads(line) for line in f if line.strip()]
ops=[e for e in events if e.get('e')=='op']
assert header['dropped_events']==0 and not header.get('open_ops')
strings=header['strings']; index={e['id']:e for e in ops}; origin=min(e['s'] for e in ops)
allowed={
    'call_exec': ['Workspace.artifacts','Artifacts.__itemsJSON','Address.container','go:Go.modules','go:GoModule.tests','ModuleSource.asModule'],
    'internal':['git.publicAdvertisement','dagql.publishResult','typescript.staticMetadata','dang.selfTypes','dang.decodeSchema','dang.invoke'],
    'session_phase':['session.query','session.schemaBuild'],
    'call':['ObjectTypeDef.__withFunction'],
    'exec_phase':['runtime'],
}
def union(xs):
    intervals=[]
    for a,b in sorted((x['s'],x['d']) for x in xs):
        if intervals and a<=intervals[-1][1]:intervals[-1][1]=max(b,intervals[-1][1])
        else:intervals.append([a,b])
    return sum(b-a for a,b in intervals)/1e6
phases=[]
for kind,names in allowed.items():
    for name in names:
        xs=[e for e in ops if e['k']==kind and strings[e.get('c',0)]==name]
        item={'kind':kind,'name':name,'count':len(xs),'inclusive_sum_ms':sum(x['d']-x['s'] for x in xs)/1e6,'interval_union_ms':union(xs)}
        if len(xs)<=25:
            item['intervals']=[{'start_ms':(x['s']-origin)/1e6,'end_ms':(x['d']-origin)/1e6,'duration_ms':(x['d']-x['s'])/1e6} for x in sorted(xs,key=lambda x:x['s'])]
        phases.append(item)
result={'profile_sha256':hashlib.sha256(PATH.read_bytes()).hexdigest(),'schema_version':header['schema_version'],'operation_count':len(ops),'dropped_events':0,'open_ops':0,'trace_window_ms':(max(x['d']for x in ops)-origin)/1e6,'phases':phases,'limits':['Separate profiled local command with Cloud export disabled; not ordinary latency.','Inclusive sums and interval unions overlap and are not predicted savings.','The analyzer what-if model has separate query roots; its roughly5ms candidates do not bound savings across this sequential CLI request chain.','Retained cache and experimental SDK/engine stack; not an unmodified main or cold run.']}
(ROOT/'engine-numeric.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k]for k in ('operation_count','dropped_events','open_ops','trace_window_ms')}))
