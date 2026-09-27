"""Reduce private clone A/B wcprof to allowlisted phase/count/interval evidence."""
from pathlib import Path
from collections import defaultdict
import argparse, hashlib, importlib.util, json

SOURCE=Path('/tmp/collections-perf/dang-admission-runtime-v1/reduce.py')
spec=importlib.util.spec_from_file_location('admission_numeric',SOURCE)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
LABELS=('dang.flushTelemetry','telemetry.flushTraces','telemetry.flushLogs','telemetry.flushMetrics','telemetry.flushClientMetrics')

def flush_analysis(profile):
 with profile.open()as f:
  header=json.loads(next(f));ops=[o for line in f if line.strip()for o in [json.loads(line)]if o.get('e')=='op']
 strings=header['strings'];name=lambda o:strings[o.get('c',0)]
 byid={o['id']:o for o in ops};children=defaultdict(list)
 for o in ops:children[o.get('p')].append(o)
 def descendants(op):
  found=[];seen=set();pending=list(children[op['id']])
  while pending:
   item=pending.pop()
   if item['id']in seen:continue
   seen.add(item['id']);found.append(item);pending.extend(children[item['id']])
  return found
 def clipped(op,windows):
  return [(max(op['s'],w['s']),min(op['d'],w['d']))for w in windows if op['s']<w['d']and op['d']>w['s']]
 expansion=[o for o in ops if name(o)=='Artifacts.__itemsJSON'and o['k']=='call_exec']
 flushes=sorted([o for o in ops if name(o)=='dang.flushTelemetry'],key=lambda o:o['s'])
 summary=[]
 for label in LABELS:
  selected=[o for o in ops if name(o)==label]
  intervals=[part for o in selected for part in clipped(o,expansion)]
  summary.append({'class':label,**base.stats(selected),'expansion_overlap_union_ms':base.union_ns(intervals)/1e6})
 rows=[];claimed=set()
 for ordinal,flush in enumerate(flushes):
  nested=descendants(flush);phases=[];covered=[]
  for label in LABELS[1:]:
   selected=[o for o in nested if name(o)==label]
   claimed.update(o['id']for o in selected)
   phases.append({'class':label,**base.stats(selected)})
   if label!='telemetry.flushClientMetrics':covered.extend((o['s'],o['d'])for o in selected)
  parent_without_phases=base.subtract([(flush['s'],flush['d'])],covered)
  rows.append({'ordinal':ordinal,'duration_ms':(flush['d']-flush['s'])/1e6,'phases':phases,'outside_phase_union_ms':base.union_ns(parent_without_phases)/1e6,'inside_expansion':any(flush['s']>=w['s']and flush['d']<=w['d']for w in expansion)})
 providers=[o for o in ops if name(o)=='telemetry.flushClientMetrics']
 barrier_providers=[o for o in providers if o['id']in claimed]
 aggregates=[o for o in ops if name(o)=='telemetry.flushMetrics'and o['id']in claimed]
 return {'fixed_classes':summary,'dang_barriers':rows,'actual_provider_forceflush_calls_in_dang_barriers':len(barrier_providers),'metrics_aggregate_calls_in_dang_barriers':len(aggregates),'provider_calls_per_barrier':[next(p['count']for p in row['phases']if p['class']=='telemetry.flushClientMetrics')for row in rows],'provider_calls_outside_dang_barriers':len(providers)-len(barrier_providers),'interpretation':'Provider marker begins after metricMu acquisition and nonnil-provider check, so it counts actual ForceFlush invocations. It does not report unique clients, changed metrics, records, or exporter requests. Aggregate phase includes scheduling and mutex wait. Parent and child wall durations overlap; no sum is a CPU or guaranteed removable latency estimate.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 rows=json.loads((a.runtime_dir/'results-numeric.json').read_text());assert len(rows)==36 and all(r['correct']for r in rows)
 profiles=[]
 for row in rows:
  if not row['profile']:continue
  file=a.runtime_dir/('block-'+str(row['block']))/('%02d-%s'%(row['index'],row['label']))/'run.wcprof.private'
  assert sha(file)==row['profile_sha256']
  numeric=base.analyze(file,row['profile_sha256']);numeric['variant']=row['variant'];numeric['flush']=flush_analysis(file)
  assert numeric['open_operations']==numeric['dropped_events']==0
  assert numeric['flush']['dang_barriers'], 'no completed Dang barrier captured'
  recorded={p['class']:p['count']for p in numeric['flush']['fixed_classes']}
  assert recorded['telemetry.flushTraces']>0 and recorded['telemetry.flushLogs']>0, 'missing common profiling markers'
  # Zero actual metric providers is a meaningful outcome, not a failed finding.
  profiles.append(numeric)
 assert len(profiles)==2 and {p['variant']for p in profiles}=={'baseline','candidate'}
 result={'reducer_sha256':sha(__file__),'admission_reducer_sha256':sha(SOURCE),'profiles':profiles,'caveats':['Separately profiled observations are not ordinary latency samples.','dang.cloneSchema is decoded schema copying, not cloneSyntax AST copying; do not conflate them.','dang.runSource includes parsing/cloning, inference, declaration and evaluation; it does not isolate the new clone implementation.','No arbitrary identifiers, module names, raw strings, client IDs, or payloads are published.','Barrier fanout counts ForceFlush calls only, not provider uniqueness or network requests.']}
 a.output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'profiles':len(profiles),'provider_calls':[p['flush']['actual_provider_forceflush_calls_in_dang_barriers']for p in profiles]}))
if __name__=='__main__':main()
