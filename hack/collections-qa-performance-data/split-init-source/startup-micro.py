#!/usr/bin/env python3
"""Prepared 30-process LOCAL startup witness; no engine/Cloud calls.

Four primers, twelve alternating pairs, two separate inittrace diagnostics.
Both binaries receive an unmatched argv[0], so neither PID1 nor helper mode runs.
This measures full host process startup/exit, never a predicted CLI saving.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import threading
import time

LAB = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run', action='store_true')
parser.add_argument('--output', default='startup-micro-v1')
args = parser.parse_args()
assert re.fullmatch(r'startup-micro-v[0-9]+', args.output)
if not args.run:
    print(json.dumps({'run': False, 'child_process_cap': 30, 'primers': 4, 'ordinary_pairs': 12, 'inittrace_diagnostics': 2, 'engine_calls': 0, 'cloud_calls': 0, 'cache_state': 'host-warm after explicit primers; no cold claim'}))
    raise SystemExit(0)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

manifest_path = LAB / 'build-results-v1/runtime-builds.json'
manifest = json.loads(manifest_path.read_text())
assert len(manifest['builds']) == 4 and all(b['exit_code'] == 0 for b in manifest['builds'].values())
binaries = {'heavy': manifest['builds']['dagger-init-common'], 'light': manifest['builds']['dagger-init-lite']}
for binary in binaries.values():
    assert sha(binary['path']) == binary['sha256']
out = LAB / args.output
out.mkdir(mode=0o700, exist_ok=False)
private = out / 'private'
private.mkdir(mode=0o700)
(private / 'home').mkdir()
env = {'PATH': '/usr/bin:/bin', 'HOME': str(private / 'home'), 'TMPDIR': str(private), 'LANG': 'C', 'TZ': 'UTC', 'GOMAXPROCS': '4'}
rows = []
result = {'manifest_sha256': sha(manifest_path), 'driver_sha256': sha(__file__), 'binaries': {k: {'sha256': v['sha256'], 'bytes': v['bytes']} for k,v in binaries.items()}, 'scope': 'same host, warm process startup+exit with unmatched argv0; no PID1/helper behavior, no engine, no Cloud, no predicted CLI gain', 'samples': rows}

def run(variant, kind, pair=None):
    assert len(rows) < 30
    stdout = private / (f'{len(rows):02}-{variant}-{kind}.stdout')
    stderr = private / (f'{len(rows):02}-{variant}-{kind}.stderr')
    childenv = dict(env)
    if kind == 'inittrace':
        childenv['GODEBUG'] = 'inittrace=1'
    with stdout.open('wb') as so, stderr.open('wb') as se:
        started = threading.Event()
        finished = threading.Event()
        state = {}
        def reap():
            started.wait()
            if 'child' not in state:
                finished.set()
                return
            try:
                _, status, usage = os.wait4(state['child'].pid, 0)
                state.update(status=status, usage=usage, end=time.perf_counter_ns())
            except BaseException as error:
                state['wait_error'] = type(error).__name__
            finally:
                finished.set()
        waiter = threading.Thread(target=reap)
        waiter.start()
        start = time.perf_counter_ns()
        timed_out = False
        launch_error = None
        try:
            child = subprocess.Popen(['split-init-unmatched'], executable=binaries[variant]['path'], stdin=subprocess.DEVNULL, stdout=so, stderr=se, env=childenv)
            state['child'] = child
            started.set()
            timed_out = not finished.wait(10)
            if timed_out:
                child.kill()
            waiter.join()
            if 'status' in state:
                child.returncode = os.waitstatus_to_exitcode(state['status'])
        except BaseException as error:
            launch_error = type(error).__name__
            if 'child' in state and not finished.is_set():
                state['child'].kill()
        finally:
            started.set()
            waiter.join()
    usage = state.get('usage')
    row = {'variant': variant, 'kind': kind, 'pair': pair, 'wall_ms': (state.get('end',time.perf_counter_ns())-start)/1e6, 'user_ms': usage.ru_utime*1000 if usage else None, 'sys_ms': usage.ru_stime*1000 if usage else None, 'maxrss_bytes': usage.ru_maxrss*1024 if usage else None, 'input_blocks': usage.ru_inblock if usage else None, 'output_blocks': usage.ru_oublock if usage else None, 'exit_code': os.waitstatus_to_exitcode(state['status']) if 'status' in state else None, 'timed_out': timed_out, 'launch_error': launch_error, 'wait_error': state.get('wait_error'), 'stdout_bytes': stdout.stat().st_size, 'stderr_bytes': stderr.stat().st_size}
    rows.append(row)
    (out / 'numeric.json').write_text(json.dumps(result, indent=2) + '\n')
    assert not timed_out and not launch_error and not row['wait_error'] and row['exit_code'] == 0 and row['stdout_bytes'] == 0
    if kind != 'inittrace':
        assert row['stderr_bytes'] == 0
    else:
        records = re.findall(r'^init .*?, ([0-9.]+) ms clock, (\d+) bytes, (\d+) allocs', stderr.read_text(), re.MULTILINE)
        row['inittrace'] = {'records': len(records), 'reported_package_clock_ms_sum': sum(float(r[0]) for r in records), 'reported_allocated_bytes_sum': sum(int(r[1]) for r in records), 'reported_allocations_sum': sum(int(r[2]) for r in records), 'private_stderr_sha256': sha(stderr)}

for _ in range(2):
    for variant in ['heavy','light']:
        run(variant, 'primer')
for pair in range(12):
    for variant in (['heavy','light'] if pair % 2 == 0 else ['light','heavy']):
        run(variant, 'ordinary', pair)
for variant in ['heavy','light']:
    run(variant, 'inittrace')
result['summary'] = {v: {field: statistics.median(r[field] for r in rows if r['variant']==v and r['kind']=='ordinary') for field in ['wall_ms','user_ms','sys_ms','maxrss_bytes']} for v in binaries}
result['completed_processes'] = len(rows)
(out / 'numeric.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'completed': len(rows), 'summary': result['summary'], 'engine_calls': 0, 'cloud_calls': 0}), flush=True)
