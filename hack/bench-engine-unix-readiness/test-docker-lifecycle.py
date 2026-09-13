#!/usr/bin/env python3
"""Check real Docker exec timeout/closure on the uniquely owned built engine.

No delayed engine startup, socket injection, image mutation or performance
claim. A local Docker client exit need not kill its container-side exec; require
that remaining helper to respect the existing finite connection timeout.
"""
import hashlib
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
BUILD = HERE/'engine-builds/builds.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    assert sys.argv[1:] == ['--execute']
    report_path = HERE/'docker-lifecycle.json'
    assert not report_path.exists(), 'preserve previous lifecycle evidence'
    build = json.loads(BUILD.read_text())
    assert build['status'] == 'built-and-query-passed'
    candidate = next(row for row in build['builds'] if row['side'] == 'B')
    name = candidate['engine_name']
    assert name == 'dagger-unix-readiness-ufjy9dsi'
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('DAGGER_', '_DAGGER_', 'OTEL_'))}
    env.pop('DOCKER_CONTEXT', None)
    env['DOCKER_HOST'] = 'unix:///var/run/docker.sock'

    def read(*argv):
        return subprocess.check_output(argv, env=env, text=True, timeout=10).strip()

    def identity():
        obj = json.loads(read('docker', 'inspect', name))[0]
        return {key: obj[key] for key in ('Id', 'Image', 'RestartCount')}

    retained = identity()
    assert retained['Id'] == candidate['engine_after_smoke']['Id']
    assert retained['Image'] == candidate['engine_after_smoke']['Image']
    report = dict(status='running', scope=__doc__, build_sha256=sha(BUILD),
                  script_sha256=sha(__file__), engine=retained, cases=[])

    def save():
        report_path.write_text(json.dumps(report, indent=2)+'\n')

    def owned_child_alive(pid, address):
        # Inspect only the positive PID reported by our own exec wrapper. A
        # reused PID with a different command is not our child; never signal it.
        argv = read('docker', 'exec', name, 'sh', '-c',
                    'if [ -r "/proc/$1/cmdline" ]; then tr "\\000" "\\n" < "/proc/$1/cmdline"; fi',
                    'sh', str(pid)).splitlines()
        return 'buildctl' in argv and address in argv

    save()
    try:
        for close_client in (False, True):
            seconds = 5 if close_client else 1
            path = '/tmp/ds-'+uuid.uuid4().hex[:12]+'.sock'
            address = 'unix://'+path
            assert not read('docker', 'exec', name, 'test', '!', '-e', path)
            argv = ['docker', 'exec', '-i', name, 'sh', '-c',
                    'printf "%s\\n" "$$"\nexec buildctl --addr "$1" --timeout "$2" dial-stdio',
                    'sh', address, str(seconds)]
            case = dict(close_local_client=close_client, timeout_seconds=seconds, address=address,
                        started_ns=time.time_ns(), argv=argv)
            report['cases'].append(case)
            save()
            child = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(child.stdout, selectors.EVENT_READ)
                    assert selector.select(3), 'Docker exec did not report its owned PID'
                    pid = int(child.stdout.readline().strip())
                assert pid > 0
                started = time.monotonic()
                case['container_child_pid'] = pid
                time.sleep(.075)
                assert child.poll() is None
                assert owned_child_alive(pid, address), 'reported exec did not enter the real dialstdio helper'
                if close_client:
                    closed = time.monotonic()
                    child.terminate()
                    stdout, stderr = child.communicate(timeout=2)
                    case['local_close_ms'] = (time.monotonic()-closed)*1000
                    assert case['local_close_ms'] < 1000
                    case['container_child_survived_local_close'] = owned_child_alive(pid, address)
                    while owned_child_alive(pid, address):
                        assert time.monotonic()-started < seconds+2, 'container helper exceeded its bounded timeout'
                        time.sleep(.1)
                    case['container_exit_observed_ms'] = (time.monotonic()-started)*1000
                else:
                    stdout, stderr = child.communicate(timeout=3)
                    case['elapsed_ms'] = (time.monotonic()-started)*1000
                    assert child.returncode == 1
                    assert 'i/o timeout' in stderr and path in stderr
                    assert 900 <= case['elapsed_ms'] < 3000
                    assert not owned_child_alive(pid, address)
                case.update(exit_code=child.returncode, stdout=stdout, stderr=stderr, passed=True)
                save()
            finally:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.communicate(timeout=2)
            assert identity() == retained
        assert all(case.get('passed') for case in report['cases'])
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=repr(error))
        raise
    finally:
        report['ended_ns'] = time.time_ns()
        save()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
