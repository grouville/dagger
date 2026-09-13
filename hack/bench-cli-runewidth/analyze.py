#!/usr/bin/env python3
"""Retain all paired timings; validate profiles and actual ordinary crate work."""
from collections import defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
EXTRACTOR=Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop/profile-command.py')
ANALYZER=Path('/tmp/dagger-rust-wcprof-otel')
CARGO=['sh','-c','rsync -rclp --delete /input/ /src/ && cargo check --workspace --locked']
EXPECTED={'exact':[], 'application':[('ripgrep','15.2.0')],
    'workspace-library':[('grep','0.4.1'),('grep-printer','0.3.1'),('ripgrep','15.2.0')]}

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def stats(values):
    return dict(n=len(values),median=statistics.median(values),minimum=min(values),maximum=max(values),
        p95=sorted(values)[math.ceil(len(values)*.95)-1],values=values)

def main():
    capture=json.loads((ROOT/'pilot.json').read_text())
    assert capture['status']=='passed'
    assert sha(ROOT/'telemetry.jsonl')==capture['telemetry_sha256']
    assert sha(ANALYZER)=='de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba'
    out=ROOT/'analysis'
    out.mkdir()
    runs={r['name']:Path(r['roots'][0]) for r in capture['runs']}
    report=dict(status='running',scope=capture['scope'],capture_sha256=sha(ROOT/'pilot.json'),
        analyzer_sha256=sha(ANALYZER),extractor_sha256=sha(EXTRACTOR),script_sha256=sha(__file__),
        timings={},profiles=[],ordinary_audits=[])
    for cohort in ('version','exact','edits'):
        rows=[r for r in csv.DictReader((runs[cohort]/'timings.csv').open()) if r['warmup']=='False']
        for scenario in sorted({r.get('scenario',cohort) for r in rows}):
            pairs=[]
            selected=[r for r in rows if r.get('scenario',cohort)==scenario]
            for sample in sorted({int(r['sample']) for r in selected}):
                pair={r['side']:float(r['milliseconds']) for r in selected if int(r['sample'])==sample}
                assert set(pair)=={'before','after'}
                pairs.append(dict(sample=sample,**pair,saved_ms=pair['before']-pair['after'],
                    ratio=pair['after']/pair['before']))
            report['timings'][scenario]=dict(pairs=pairs,saved_ms=stats([p['saved_ms'] for p in pairs]),
                ratio=stats([p['ratio'] for p in pairs]),before_ms=stats([p['before'] for p in pairs]),
                after_ms=stats([p['after'] for p in pairs]),
                favorable=sum(p['saved_ms']>0 for p in pairs))
    for cohort in ('exact-profiled','edits-profiled','edits'):
        processes=[json.loads(line) for line in (runs[cohort]/'processes.jsonl').read_text().splitlines()]
        profiled=cohort.endswith('profiled')
        for process in processes:
            if not process.get('timed',True):
                continue
            label=process['label']
            name=cohort+'-'+label
            trace=out/(name+'.trace.jsonl')
            extraction=subprocess.run([sys.executable,str(EXTRACTOR),'--processes',str(runs[cohort]/'processes.jsonl'),
                '--otel',str(ROOT/'telemetry.jsonl'),'--label',label,'--output',str(trace)],text=True,capture_output=True)
            (out/(name+'.extraction.txt')).write_text(extraction.stdout+extraction.stderr)
            assert extraction.returncode==0,name
            envelope=json.loads(extraction.stdout)
            spans={}
            logs=[]
            for line in trace.read_text().splitlines():
                row=json.loads(line)
                if row['kind']=='span' and row.get('endNs',0)>=spans.get(row['spanId'],{}).get('endNs',0):
                    spans[row['spanId']]=row
                elif row['kind']=='log':
                    logs.append(row)
            execs=[]
            for span in spans.values():
                attrs=span.get('attrs',{})
                if span['name']=='exec.processRun' and attrs.get('wcprof.op.kind')=='exec_phase':
                    parent=spans.get(span.get('parentId'),{})
                    exits=[e.get('attrs',{}).get('exit.code') for e in parent.get('events',[])
                           if e['name']=='Container exited']
                    execs.append(dict(argv=json.loads(attrs['wcprof.exec.argv']),exits=exits,
                        ms=(span['endNs']-span['startNs'])/1e6))
            streams=defaultdict(str)
            for row in sorted(logs,key=lambda x:x['timeNs']):
                if row.get('scope')=='dagger.io/engine.buildkit' and row.get('attrs',{}).get('stdio.stream')==2:
                    streams[row['spanId']]+=row.get('body','')
            text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','','\n'.join(streams.values()))
            packages=sorted(set(re.findall(r'^\s*(?:Checking|Compiling) (\S+) v([^\s]+)',text,re.MULTILINE)))
            scenario=process.get('scenario','exact')
            expected=EXPECTED[scenario]
            # First application warmup after a repaired immutable hit can revisit
            # a mutable failure state from the primer; keep and label, never time it.
            warmup=process.get('warmup',label.endswith('-0'))
            packages_ok=(set(expected)<=set(packages) if warmup and scenario!='exact' else packages==expected)
            exec_ok=(not execs if scenario=='exact' else len(execs)==1 and execs[0]['argv']==CARGO and execs[0]['exits']==[0])
            no_image=not any(s['name'].startswith(('pulling ','preparing pull ','unpacking ')) for s in spans.values())
            detail=dict(envelope,cohort=cohort,scenario=scenario,label=label,side=process.get('side',label.split('-')[0]),
                sample=process.get('sample',int(label.split('-')[-1]) if cohort=='exact-profiled' else None),
                warmup=warmup,execs=execs,packages=packages,packages_ok=packages_ok,
                exec_ok=exec_ok,no_image=no_image,profiled=profiled)
            gates=packages_ok and exec_ok and no_image
            if profiled:
                analysis=subprocess.run([str(ANALYZER),'-top','60','-chain-depth','40',str(trace)],
                    text=True,capture_output=True)
                (out/(name+'.analysis.txt')).write_text(analysis.stdout)
                (out/(name+'.gate.txt')).write_text(analysis.stderr)
                markers=[s for s in spans.values() if s.get('attrs',{}).get('wcprof.session_complete')]
                declared=sum(int(s['attrs']['wcprof.session_span_count']) for s in markers)
                received=sum(bool(s.get('attrs',{}).get('wcprof.engine_span')) for s in spans.values())
                complete=analysis.returncode==0 and 'structural gate: PASS' in analysis.stderr and bool(markers) and declared==received
                detail.update(complete=complete,declared=declared,received=received,
                    replay_drift=re.search(r'drift vs actual: ([^)]+)',analysis.stdout)[1])
                gates=gates and complete
            detail['all_gates_pass']=gates
            report['profiles' if profiled else 'ordinary_audits'].append(detail)
            print(name,'PASS' if gates else 'FAIL',flush=True)
    report['all_gates_pass']=(len(report['profiles'])==24 and len(report['ordinary_audits'])==44
        and all(r['all_gates_pass'] for key in ('profiles','ordinary_audits') for r in report[key]))
    report['status']='passed' if report['all_gates_pass'] else 'failed'
    (ROOT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['all_gates_pass']
    print(json.dumps({key:{'saved_ms':v['saved_ms'],'favorable':v['favorable'],
        'before_ms':v['before_ms']['median'],'after_ms':v['after_ms']['median']} for key,v in report['timings'].items()},indent=2))

if __name__=='__main__':main()
