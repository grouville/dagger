#!/usr/bin/env python3
"""Check complete wcprof profiles and actual setup reuse, not performance."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
EXTRACT=Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop/profile-command.py')
WCPROF=Path('/tmp/dagger-rust-wcprof-otel')
CARGO=['sh','-c','rsync -rclp --delete /input/ /src/ && cargo check --workspace --locked']
RUSTUP=['rustup','toolchain','install','--no-self-update']

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    meta=json.loads((ROOT/'toolchain-capture.json').read_text())
    assert meta['status']=='passed'
    assert sha(WCPROF)=='de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba'
    raw=ROOT/'toolchain-telemetry.jsonl'
    assert sha(raw)==meta['telemetry_sha256']
    fixture=Path(meta['root'])
    procs=[json.loads(line) for line in (fixture/'processes.jsonl').read_text().splitlines()]
    checks=[p for p in procs if p['command']==['--profile','check','rust:check']]
    assert len(checks)==11
    output=ROOT/'toolchain-analysis'
    output.mkdir()
    report=dict(scope=__doc__,script_sha256=sha(__file__),extractor_sha256=sha(EXTRACT),
        wcprof_sha256=sha(WCPROF),raw_sha256=sha(raw),profiles=[])
    for proc in checks:
        label=proc['label']
        prefix=output/label
        trace=Path(str(prefix)+'.trace.jsonl')
        extract=subprocess.run([sys.executable,str(EXTRACT),'--processes',str(fixture/'processes.jsonl'),
            '--otel',str(raw),'--label',label,'--output',str(trace)],text=True,capture_output=True)
        Path(str(prefix)+'.extraction.txt').write_text(extract.stdout+extract.stderr)
        assert extract.returncode==0, label
        analysis=subprocess.run([str(WCPROF),'-top','60','-chain-depth','40',str(trace)],text=True,capture_output=True)
        Path(str(prefix)+'.analysis.txt').write_text(analysis.stdout)
        Path(str(prefix)+'.gate.txt').write_text(analysis.stderr)
        spans={}
        for line in trace.read_text().splitlines():
            row=json.loads(line)
            if row.get('kind')=='span':
                old=spans.get(row['spanId'])
                if old is None or row.get('endNs',0)>=old.get('endNs',0): spans[row['spanId']]=row
        markers=[s for s in spans.values() if s.get('attrs',{}).get('wcprof.session_complete')]
        declared=sum(int(s['attrs']['wcprof.session_span_count']) for s in markers)
        received=sum(bool(s.get('attrs',{}).get('wcprof.engine_span')) for s in spans.values())
        drift=re.search(r'drift vs actual: ([^)]+)',analysis.stdout)
        row=dict(label=label,process_exit=proc['exit_code'],declared=declared,received=received,
            structural_pass=analysis.returncode==0 and 'structural gate: PASS' in analysis.stderr and bool(markers) and declared==received,
            replay_drift=drift[1] if drift else None,execs=[],host_directory_calls=[])
        for span in spans.values():
            attrs=span.get('attrs',{})
            if span['name']=='exec.processRun' and attrs.get('wcprof.op.kind')=='exec_phase':
                parent=spans.get(span.get('parentId'),{})
                exits=[event.get('attrs',{}).get('exit.code') for event in parent.get('events',[]) if event['name']=='Container exited']
                row['execs'].append(dict(argv=json.loads(attrs['wcprof.exec.argv']),exit_codes=exits,
                    within_process=proc['start_unix_ns']<=span['startNs']<=span['endNs']<=proc['end_unix_ns']))
            if span['name']=='Host.directory' and attrs.get('wcprof.op.kind')=='call_exec':
                row['host_directory_calls'].append(span['spanId'])
        row['cargo']=[e for e in row['execs'] if e['argv']==CARGO]
        row['rustup']=[e for e in row['execs'] if e['argv']==RUSTUP]
        row['source_edit_reuses_toolchain']=label not in ('source-failure','source-repair') or (
            not row['rustup'] and len(row['cargo'])==1 and row['cargo'][0]['exit_codes']==[101 if label=='source-failure' else 0])
        row['config_change_runs_setup']=label not in ('initial-fmt','add-clippy','legacy-file') or len(row['rustup'])==1
        row['exact_repair_reuses_action']=label!='final-repair' or not row['execs']
        row['all_local_gates']=all(row[k] for k in ('structural_pass','source_edit_reuses_toolchain','config_change_runs_setup','exact_repair_reuses_action')) and all(e['within_process'] for e in row['execs'])
        report['profiles'].append(row)
        print(label,'complete',row['structural_pass'],'rustup',len(row['rustup']),'cargo',len(row['cargo']),'gates',row['all_local_gates'],flush=True)
    report['passed']=len(report['profiles'])==11 and all(r['all_local_gates'] for r in report['profiles'])
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['passed'],'retained failed profile/correctness evidence'

if __name__=='__main__': main()
