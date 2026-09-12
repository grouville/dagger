#!/usr/bin/env python3
"""Gate the exact-hit pilot and report paired CLI and connection timings."""
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys

ROOT=Path(sys.argv[1]).resolve()
EXTRACTOR=Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop/profile-command.py')
ANALYZER=Path('/tmp/dagger-rust-wcprof-otel')

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def stats(values):
    return dict(n=len(values),median=statistics.median(values),minimum=min(values),maximum=max(values),values=values)

def main():
    capture=json.loads((ROOT/'pilot.json').read_text())
    assert capture['status']=='passed'
    assert sha(ANALYZER)=='de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba'
    assert sha(ROOT/'telemetry.jsonl')==capture['telemetry_sha256']
    out=ROOT/'analysis';out.mkdir()
    report=dict(status='running',scope='Local Docker exact-hit CLI preconnection pilot, not cold/native/invalidation.',
        capture=capture,analyzer_sha256=sha(ANALYZER),extractor_sha256=sha(EXTRACTOR),profiles=[])
    profiled=Path(next(r['root'] for r in capture['runs'] if r['profiled']))
    for process in map(json.loads,(profiled/'processes.jsonl').read_text().splitlines()):
        label=process['label'];prefix=out/label;trace=out/(label+'.trace.jsonl')
        extraction=subprocess.run([sys.executable,str(EXTRACTOR),'--processes',str(profiled/'processes.jsonl'),
            '--otel',str(ROOT/'telemetry.jsonl'),'--label',label,'--output',str(trace)],text=True,capture_output=True)
        (out/(label+'.extraction.txt')).write_text(extraction.stdout+extraction.stderr)
        assert extraction.returncode==0
        result=subprocess.run([str(ANALYZER),'-top','60','-chain-depth','40',str(trace)],text=True,capture_output=True)
        (out/(label+'.analysis.txt')).write_text(result.stdout)
        (out/(label+'.gate.txt')).write_text(result.stderr)
        spans={}
        for row in map(json.loads,trace.read_text().splitlines()):
            if row['kind']=='span' and row.get('endNs',0)>=spans.get(row['spanId'],{}).get('endNs',0):spans[row['spanId']]=row
        markers=[s for s in spans.values() if s.get('attrs',{}).get('wcprof.session_complete')]
        declared=sum(int(s['attrs']['wcprof.session_span_count']) for s in markers)
        received=sum(bool(s.get('attrs',{}).get('wcprof.engine_span')) for s in spans.values())
        actual_execs=[s for s in spans.values() if s['name']=='exec.processRun' and s.get('attrs',{}).get('wcprof.op.kind')=='exec_phase']
        exec_outcomes=[s.get('attrs',{}).get('dagger.io/cache.outcome') for s in spans.values() if s['name']=='Container.withExec']
        image=[s['name'] for s in spans.values() if s['name'].startswith(('pulling ','preparing pull ','unpacking '))]
        startup=[dict(name=s['name'],start_ns=s['startNs'],end_ns=s['endNs'],ms=(s['endNs']-s['startNs'])/1e6)
            for s in spans.values() if s['name'] in ('connect','connecting to engine','starting session','consuming /v1/traces','exec docker version')]
        detail=dict(json.loads(extraction.stdout),declared=declared,received=received,actual_execs=len(actual_execs),
            exec_outcomes=exec_outcomes,image_spans=image,startup=startup,
            replay_drift=re.search(r'drift vs actual: ([^)]+)',result.stdout)[1],
            pass_gate=result.returncode==0 and 'structural gate: PASS' in result.stderr and bool(markers) and declared==received
                and not actual_execs and bool(exec_outcomes) and all(x=='hit' for x in exec_outcomes) and not image)
        report['profiles'].append(detail)
        print(label,detail['pass_gate'],detail['replay_drift'],flush=True)
    unprofiled=Path(next(r['root'] for r in capture['runs'] if not r['profiled']))
    timed=[r for r in csv.DictReader((unprofiled/'timings.csv').open()) if r['warmup']=='False']
    pairs=[]
    for sample in sorted({int(r['sample']) for r in timed}):
        pair={r['side']:float(r['milliseconds']) for r in timed if int(r['sample'])==sample}
        assert set(pair)=={'before','after'}
        pairs.append(dict(sample=sample,**pair,saved_ms=pair['before']-pair['after']))
    report.update(pairs=pairs,paired_saving_ms=stats([p['saved_ms'] for p in pairs]),
        favorable_pairs=sum(p['saved_ms']>0 for p in pairs),
        before_ms=stats([p['before'] for p in pairs]),after_ms=stats([p['after'] for p in pairs]))
    report['all_gates_pass']=len(report['profiles'])==8 and all(p['pass_gate'] for p in report['profiles'])
    report['status']='passed' if report['all_gates_pass'] else 'failed'
    (ROOT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['all_gates_pass']
    print(json.dumps({k:report[k] for k in ('status','paired_saving_ms','favorable_pairs','before_ms','after_ms')},indent=2))

if __name__=='__main__':main()
