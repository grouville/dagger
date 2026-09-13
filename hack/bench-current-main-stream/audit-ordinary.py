#!/usr/bin/env python3
"""Audit actual execution in each ordinary timed command, not retrieved stderr.

These traces omit --profile. Profiled companions supply the separate wcprof
completeness/replay gates; ordinary traces prove the execution observed here.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

EXTRACTOR=Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop/profile-command.py')
CARGO=['sh','-c','rsync -rclp --delete /input/ /src/ && cargo check --workspace --locked']
EXPECTED={'exact':[], 'application':[('ripgrep','15.2.0')],
          'workspace-library':[('grep','0.4.1'),('grep-printer','0.3.1'),('ripgrep','15.2.0')]}

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    cohort=Path(sys.argv[1]).resolve(strict=True)
    assert cohort.parent==Path('/tmp') and cohort.name.startswith('dagger-rust-current-stream-ab-')
    meta=json.loads((cohort/'cohort.json').read_text())
    assert meta['status']=='passed' and len(meta['runs'])==6
    raw=Path(meta['telemetry'])
    assert sha(raw)==meta['telemetry_sha256']
    out=cohort/'ordinary-exec-audit';out.mkdir()
    report=dict(scope=__doc__,script_sha256=sha(__file__),extractor_sha256=sha(EXTRACTOR),
                telemetry_sha256=sha(raw),checks=[])
    for run in meta['runs']:
        root=Path(run['root'])
        for scenario,expected in EXPECTED.items():
            for sample in range(3):
                label=f'{scenario}-{sample}-dagger'
                prefix=f'{run["index"]}-{run["side"]}-{label}'
                trace=out/(prefix+'.trace.jsonl')
                result=subprocess.run([sys.executable,str(EXTRACTOR),'--processes',str(root/'processes.jsonl'),
                    '--otel',str(raw),'--label',label,'--output',str(trace)],text=True,capture_output=True)
                (out/(prefix+'.extraction.txt')).write_text(result.stdout+result.stderr)
                assert result.returncode==0,prefix
                envelope=json.loads(result.stdout)
                spans={};logs=[]
                for line in trace.read_text().splitlines():
                    row=json.loads(line)
                    if row['kind']=='span' and row.get('endNs',0)>=spans.get(row['spanId'],{}).get('endNs',0):
                        spans[row['spanId']]=row
                    elif row['kind']=='log':logs.append(row)
                execs=[]
                for span in spans.values():
                    attrs=span.get('attrs',{})
                    if span['name']=='exec.processRun' and attrs.get('wcprof.op.kind')=='exec_phase':
                        parent=spans.get(span.get('parentId'),{})
                        exits=[e.get('attrs',{}).get('exit.code') for e in parent.get('events',[]) if e['name']=='Container exited']
                        execs.append(dict(argv=json.loads(attrs['wcprof.exec.argv']),exits=exits))
                streams=defaultdict(str)
                for row in sorted(logs,key=lambda r:r['timeNs']):
                    if row.get('scope')=='dagger.io/engine.buildkit' and row.get('attrs',{}).get('stdio.stream')==2:
                        streams[row['spanId']]+=row.get('body','')
                stderr=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','','\n'.join(streams.values()))
                packages=sorted(set(re.findall(r'^\s*(?:Checking|Compiling) (\S+) v([^\s]+)',stderr,re.MULTILINE)))
                exec_ok=(not execs if scenario=='exact' else len(execs)==1 and execs[0]['argv']==CARGO and execs[0]['exits']==[0])
                # An exact hit can replay cached stderr. No process execution is
                # required there; novel edits must match actual emitted packages.
                packages_ok=scenario=='exact' or packages==expected
                no_image=not any(s['name'].startswith(('pulling ','preparing pull ','unpacking ')) for s in spans.values())
                passed=exec_ok and packages_ok and no_image
                report['checks'].append(dict(index=run['index'],side=run['side'],scenario=scenario,sample=sample,
                    envelope=envelope,execs=execs,packages=packages,exec_ok=exec_ok,packages_ok=packages_ok,
                    no_image=no_image,passed=passed))
                print(prefix,'PASS' if passed else 'FAIL',flush=True)
    report['all_pass']=len(report['checks'])==54 and all(r['passed'] for r in report['checks'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['all_pass']

if __name__=='__main__':main()
