#!/usr/bin/env python3
"""Post-capture CLI driver costs; actual spans, not predicted speed savings."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

owner = Path(__file__).resolve().parent
cohort = Path(sys.argv[1]).resolve(strict=True)
assert cohort.parent == Path('/tmp') and cohort.name.startswith('dagger-rust-cli-autoprovision-ab-')
meta = json.loads((cohort/'cohort.json').read_text())
profiles = json.loads((cohort/'analysis-r2/report.json').read_text())
ordinary = json.loads((cohort/'ordinary-exec-audit/report.json').read_text())
assert meta['status']=='passed' and profiles['all_captures_pass'] and ordinary['all_pass']
assert len(profiles['profiles'])==36 and len(ordinary['checks'])==54

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

samples = []
for check in ordinary['checks']:
    prefix = f'{check["index"]}-{check["side"]}-{check["scenario"]}-{check["sample"]}-dagger'
    samples.append(dict(index=check['index'], side=check['side'], flow=check['scenario'],
        iteration=check['sample'], profiled=False, process_ms=check['envelope']['process_ms'],
        trace=str(cohort/'ordinary-exec-audit'/(prefix+'.trace.jsonl'))))
for check in profiles['profiles']:
    if check['label'] in ('warmup-dagger','dependency-upgrade-dagger','profile-restart-exact'):
        prefix = f'{check["index"]}-{check["side"]}-{check["label"]}'
        samples.append(dict(index=check['index'], side=check['side'], flow=check['label'],
            iteration=0, profiled=True, process_ms=check['process_ms'],
            trace=str(cohort/'analysis-r2'/(prefix+'.trace.jsonl'))))

for sample in samples:
    spans = {}
    for line in Path(sample['trace']).read_text().splitlines():
        row = json.loads(line)
        if row['kind']=='span' and row.get('endNs',0)>=spans.get(row['spanId'],{}).get('endNs',0):
            spans[row['spanId']]=row
    root = [s for s in spans.values() if s.get('scope')=='dagger.io/cli' and not s.get('parentId')]
    assert len(root)==1
    connects = [s for s in spans.values() if s['name']=='connect' and s.get('parentId')==root[0]['spanId']]
    clients = [s for s in spans.values() if s['name']=='creating client' and s.get('scope')=='dagger.io/engine.client']
    assert len(connects)==len(clients)==1
    duration = lambda s:(s['endNs']-s['startNs'])/1e6
    sample['connect_ms']=duration(connects[0])
    sample['creating_client_ms']=duration(clients[0])
    commands=sorted((s for s in spans.values() if s['name'].startswith('exec docker ')),key=lambda s:s['startNs'])
    sample['docker_commands']=[dict(name=s['name'],ms=duration(s),start_ns=s['startNs'],end_ns=s['endNs'],
        status=s.get('status')) for s in commands]
    assert all(a['endNs']<=b['startNs'] for a,b in zip(commands,commands[1:])), 'overlapping driver subprocesses must not be summed as serial overhead'
    sample['docker_exec_ms']=sum(duration(s) for s in commands)
    for key,prefix in (('runtime_probe_ms','exec docker version'),('list_ms','exec docker ps '),('start_ms','exec docker start ')):
        matching=[s for s in commands if s['name'].startswith(prefix)]
        sample[key]=sum(duration(s) for s in matching)
        sample[key+'_count']=len(matching)

groups=defaultdict(list)
for sample in samples:
    groups[sample['flow'],sample['side'],sample['index']].append(sample)
fields=('process_ms','connect_ms','creating_client_ms','docker_exec_ms','runtime_probe_ms','list_ms','start_ms')
per_run=[dict(flow=flow,side=side,index=index,n=len(rows),
    **{key:statistics.median(r[key] for r in rows) for key in fields})
    for (flow,side,index),rows in groups.items()]
summary={}
for flow in sorted({r['flow'] for r in per_run}):
    summary[flow]={}
    for side in ('A','B'):
        rows=[r for r in per_run if r['flow']==flow and r['side']==side]
        assert len(rows)==3
        summary[flow][side]={key:dict(median=statistics.median(r[key] for r in rows),
            minimum=min(r[key] for r in rows),maximum=max(r[key] for r in rows)) for key in fields}
result=dict(scope=__doc__,script_sha256=sha(__file__),source_report_sha256=sha(cohort/'analysis-r2/report.json'),
    ordinary_report_sha256=sha(cohort/'ordinary-exec-audit/report.json'),samples=samples,per_run=per_run,summary=summary,
    limits=['Analysis frozen before capture; raw telemetry and timing controllers unchanged',
            'Warm repeats summarized within each run before three-run medians',
            'Docker subprocess spans can include multiple kinds of work; eliminating a command is not yet a measured optimization',
            'Creating-client includes uninstrumented connection-proxy startup, transport and Info; do not add it to enclosing connect',
            'This cohort retains ordinary image-driver lookup/start for every command; not the previous container:// baseline'])
with (owner/'driver-summary.json').open('x') as stream:
    json.dump(result,stream,indent=2);stream.write('\n')
print(json.dumps(summary,indent=2))
