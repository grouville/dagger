#!/usr/bin/env python3
"""Validate every retained wcprof exact-check capture, not selected samples."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
EXTRACTOR = Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop/profile-command.py')
WCPROF = Path('/tmp/dagger-rust-wcprof-otel')

def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def main():
    capture = json.loads((HERE/'capture.json').read_text())
    assert capture['status'] == 'captured'
    assert sha(HERE/'telemetry.jsonl') == capture['telemetry_sha256']
    assert sha(WCPROF) == 'de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba'
    out = HERE/'analysis'
    out.mkdir()
    profiles = []
    for run in capture['runs']:
        if not run['profiled']:
            continue
        label = run['label']
        trace = out/(label+'.trace.jsonl')
        extracted = subprocess.run([sys.executable, str(EXTRACTOR), '--processes', str(HERE/'processes.jsonl'),
            '--otel', str(HERE/'telemetry.jsonl'), '--label', label, '--output', str(trace)],
            text=True, capture_output=True)
        (out/(label+'.extraction.txt')).write_text(extracted.stdout+extracted.stderr)
        assert extracted.returncode == 0
        analyzed = subprocess.run([str(WCPROF), '-top', '60', '-chain-depth', '40', str(trace)],
            text=True, capture_output=True)
        (out/(label+'.analysis.txt')).write_text(analyzed.stdout)
        (out/(label+'.gate.txt')).write_text(analyzed.stderr)
        spans = {}
        for line in trace.read_text().splitlines():
            row = json.loads(line)
            if row['kind'] == 'span' and row.get('endNs', 0) >= spans.get(row['spanId'], {}).get('endNs', 0):
                spans[row['spanId']] = row
        markers = [s for s in spans.values() if s.get('attrs', {}).get('wcprof.session_complete')]
        declared = sum(int(s['attrs']['wcprof.session_span_count']) for s in markers)
        received = sum(bool(s.get('attrs', {}).get('wcprof.engine_span')) for s in spans.values())
        actual_execs = [s for s in spans.values() if s['name'] == 'exec.processRun' and
            s.get('attrs', {}).get('wcprof.op.kind') == 'exec_phase']
        execs = [s.get('attrs', {}).get('dagger.io/cache.outcome') for s in spans.values() if s['name'] == 'Container.withExec']
        images = [s['name'] for s in spans.values() if s['name'].startswith(('pulling ', 'preparing pull ', 'unpacking '))]
        detail = dict(json.loads(extracted.stdout), declared=declared, received=received,
            actual_execs=len(actual_execs), exec_outcomes=execs, images=images,
            drift=re.search(r'drift vs actual: ([^)]+)', analyzed.stdout)[1],
            passed=analyzed.returncode == 0 and 'structural gate: PASS' in analyzed.stderr and
                bool(markers) and declared == received and not actual_execs and bool(execs) and
                all(x == 'hit' for x in execs) and not images)
        profiles.append(detail)
        print(label, detail['passed'], detail['drift'], flush=True)
    result = dict(scope=capture['scope'], profiles=profiles, script_sha256=sha(__file__),
        capture_sha256=sha(HERE/'capture.json'), extractor_sha256=sha(EXTRACTOR),
        wcprof_sha256=sha(WCPROF), all_gates_pass=len(profiles) == 25 and all(p['passed'] for p in profiles),
        limitations=['Diagnostic only, no paired speed comparison.',
            'subprocess.run(timeout=120) polls with backoff and can overestimate process elapsed time; wcprof root spans are separately recorded.',
            'CPU profile includes all engine work in its window; not child-process CPU.',
            'Actual CPU profile start/duration must be checked independently against process intervals.'])
    (HERE/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
    assert result['all_gates_pass']

if __name__ == '__main__':
    main()
