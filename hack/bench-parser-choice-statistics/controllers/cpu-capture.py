#!/usr/bin/env python3
"""Repeated standalone exact checks with wcprof and an aligned engine CPU window.

Diagnostic only: deliberately prepared caches and extra CPU sampling; no A/B,
native comparison, cold-start score or inferred speedup.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
CLI = Path('/tmp/dagger-http-preconnect-main.tRLouH4d/dagger-candidate')
RECEIVER = Path('/tmp/dagger-rust-perf-sprint.1qnbuQ9j/otlpdump')
ENGINE = 'dagger-engine.rust-fresh-qeptezyl'
IDENTITY = 'ff1caa52447eaf97c9b97b1d7b8765b3679bb956af1298821759dab0e29b6f1e sha256:3df4828f5969eef38ec13cf445e2eb1f161d0e7f2f16606a863fe30a27a44181 true'
ENDPOINT = 'http://127.0.0.1:43228'
PROJECT = HERE / 'project'
PINS = {
    CLI: '23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270',
    RECEIVER: 'f2aef556572da41578a0336248b4c6d1972b9d050df2622e57303555752f9b38',
}


def sha(path):
    with Path(path).open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()


def main():
    assert sys.argv[1:] == ['--execute']
    assert not (HERE/'capture.json').exists()
    for path, digest in PINS.items():
        assert sha(path) == digest
    env = {k: v for k, v in os.environ.items() if not k.startswith(
        ('GIT_', 'DAGGER_', '_DAGGER_', '_EXPERIMENTAL_DAGGER_', 'OTEL_'))}
    env.pop('DOCKER_CONTEXT', None)
    env.update(DO_NOT_TRACK='1', DNT='1', DAGGER_NO_NAG='1',
               DOCKER_HOST='unix:///var/run/docker.sock', DAGGER_ENGINE='container://'+ENGINE)
    for kind in ('CONFIG', 'CACHE', 'DATA', 'STATE'):
        env['XDG_'+kind+'_HOME'] = str(HERE/'cli-state'/kind.lower())
    inspect = ['docker', 'inspect', '--format', '{{.Id}} {{.Image}} {{.State.Running}}', ENGINE]
    assert subprocess.check_output(inspect, env=env, text=True).strip() == IDENTITY
    ip = subprocess.check_output(['docker', 'inspect', '--format',
        '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', ENGINE], env=env, text=True).strip()
    assert ip.startswith('172.17.') and len(ip.split('.')) == 4
    debug = 'http://'+ip+':6060'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(debug+'/debug/pprof/cmdline', timeout=3) as response:
        assert response.read().startswith(b'/usr/local/bin/dagger-engine\0')
    shutil.copytree('/tmp/dagger-http-preconnect-main.tRLouH4d/pilot/project', PROJECT,
                    ignore=shutil.ignore_patterns('.git', 'target'))
    subprocess.run(['git', 'init', '-q'], cwd=PROJECT, env=env, check=True)
    assert subprocess.check_output(['git', 'rev-parse', '--show-toplevel'],
        cwd=PROJECT, env=env, text=True).strip() == str(PROJECT)
    source_hashes = {str(p.relative_to(PROJECT)): sha(p)
        for p in PROJECT.rglob('*') if p.is_file() and '.git' not in p.relative_to(PROJECT).parts}
    record = dict(status='running', scope=__doc__, engine=IDENTITY, debug=debug,
        script_sha256=sha(__file__), pins={str(k): v for k, v in PINS.items()},
        project_source_hashes=source_hashes, runs=[], started_ns=time.time_ns())
    def save():
        (HERE/'capture.json').write_text(json.dumps(record, indent=2)+'\n')
    def run(label, profiled):
        argv = [str(CLI)] + (['--profile'] if profiled else []) + ['check', 'rust:check']
        with (HERE/(label+'.log')).open('xb') as out:
            wall, start = time.time_ns(), time.perf_counter_ns()
            result = subprocess.run(argv, cwd=PROJECT, env=env, stdout=out, stderr=subprocess.STDOUT, timeout=120)
            end, wall_end = time.perf_counter_ns(), time.time_ns()
        item = dict(label=label, command=argv, start_unix_ns=wall, end_unix_ns=wall_end,
            milliseconds=(end-start)/1e6, exit_code=result.returncode, profiled=profiled)
        record['runs'].append(item)
        with (HERE/'processes.jsonl').open('a') as out:
            out.write(json.dumps(item)+'\n')
        save()
        assert result.returncode == 0, label
        print(label, round(item['milliseconds'], 3), flush=True)
    save()
    receiver = None
    cpu_thread = None
    try:
        run('explicit-preparation', False)
        env.update(OTEL_EXPORTER_OTLP_ENDPOINT=ENDPOINT,
            OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=ENDPOINT+'/v1/logs',
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=ENDPOINT+'/v1/metrics',
            OTEL_EXPORTER_OTLP_TRACES_LIVE='1')
        with (HERE/'receiver.log').open('xb') as out:
            receiver = subprocess.Popen([str(RECEIVER), '-addr', '127.0.0.1:43228',
                '-out', str(HERE/'telemetry.jsonl')], env=env, stdout=out, stderr=subprocess.STDOUT)
        record['receiver_pid'] = receiver.pid
        for attempt in range(100):
            assert receiver.poll() is None
            try:
                with opener.open(ENDPOINT+'/v1/traces', timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                if attempt == 99:
                    raise
                time.sleep(.05)
        run('wcprof-reference', True)
        cpu_started = threading.Event()
        cpu = dict(status='running')
        record['cpu'] = cpu
        def sample_cpu():
            cpu['request_start_ns'] = time.time_ns()
            cpu_started.set()
            try:
                with opener.open(debug+'/debug/pprof/profile?seconds=20', timeout=30) as response:
                    data = response.read()
                    assert response.status == 200 and data.startswith(b'\x1f\x8b')
                with (HERE/'engine.cpu.pprof').open('xb') as out:
                    out.write(data)
                cpu.update(status='passed', bytes=len(data), sha256=sha(HERE/'engine.cpu.pprof'))
            except BaseException as error:
                cpu.update(status='failed', error=repr(error))
            finally:
                cpu['request_end_ns'] = time.time_ns()
        cpu_thread = threading.Thread(target=sample_cpu, daemon=True)
        cpu_thread.start()
        assert cpu_started.wait(timeout=5)
        # Record the request interval; do not pretend this notification is a
        # server acknowledgement. Actual pprof start/duration will be checked.
        for index in range(24):
            run(f'exact-{index:02d}', True)
        cpu_thread.join(timeout=30)
        assert not cpu_thread.is_alive() and cpu['status'] == 'passed'
        assert subprocess.check_output(inspect, env=env, text=True).strip() == IDENTITY
        assert source_hashes == {str(p.relative_to(PROJECT)): sha(p)
            for p in PROJECT.rglob('*') if p.is_file() and '.git' not in p.relative_to(PROJECT).parts}
        record['status'] = 'captured'
    except BaseException as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        if cpu_thread:
            cpu_thread.join(timeout=35)
        if receiver:
            receiver.terminate()
            try:
                receiver.wait(timeout=10)
            except subprocess.TimeoutExpired:
                receiver.kill()
                receiver.wait()
            record['receiver_exit_code'] = receiver.returncode
        raw = HERE/'telemetry.jsonl'
        if raw.exists():
            record.update(telemetry_bytes=raw.stat().st_size, telemetry_sha256=sha(raw))
        record['ended_ns'] = time.time_ns()
        save()


if __name__ == '__main__':
    main()
