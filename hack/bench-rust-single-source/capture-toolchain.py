#!/usr/bin/env python3
"""Profile the existing toolchain correctness sequence on the single-source module.

No A/B latency, cold-start or native-performance claim. Uses only the newly owned
candidate engine, with a new project/cache key. Does not reset any existing cache.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
BUILD = Path('/tmp/dagger-parser-stats.I2WPGLrS/engine-builds/builds.json')
CLI = Path('/tmp/dagger-http-preconnect-main.tRLouH4d/dagger-candidate')
RECEIVER = Path('/tmp/dagger-rust-perf-sprint.1qnbuQ9j/otlpdump')
ENGINE = 'dagger-parser-stats-i2wpglrs-b'
IMAGE = 'sha256:c057d7eed790760d88e4cffb0f540adb9e230823b81759c0e86eeaae49d141a0'
ENDPOINT = 'http://127.0.0.1:43231'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    assert sys.argv[1:] == ['--execute']
    assert not (ROOT/'toolchain-capture.json').exists()
    assert sha(BUILD) == '1649132cebec1a3afd6285dd072aa2fa1557d65b84fc30ea8db603b090f6539a'
    build = json.loads(BUILD.read_text())
    source = Path(next(row['source'] for row in build['builds'] if row['side']=='B'))
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==build['parent']
    for path, expected in build['source_hashes']['B'].items():
        assert sha(source/path)==expected, path
    pins = {
        CLI:'23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270',
        RECEIVER:'f2aef556572da41578a0336248b4c6d1972b9d050df2622e57303555752f9b38',
        ROOT/'candidate/main.dang':'591d98754a680f4199c807043fdf2fc471cd3139530f75fc80a5f3f1f2b7d1e5',
        ROOT/'candidate/dagger-module.toml':'80ceb12a068bb2c86041ba35bdcb24edada8ae228b77450de2ce917caa2ec8e5',
        ROOT/'test-toolchain-profiled.py':'d33063f2309ab3f71404868583a9953d8adf4bc0ba16fcbe548a6d0d591defcb',
    }
    assert all(sha(path)==expected for path,expected in pins.items())
    env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','DAGGER_','_DAGGER_','_EXPERIMENTAL_DAGGER_','OTEL_'))}
    env.pop('DOCKER_CONTEXT',None)
    env.update(DO_NOT_TRACK='1',DNT='1',DOCKER_HOST='unix:///var/run/docker.sock',
        DAGGER_ENGINE='container://'+ENGINE,OTEL_EXPORTER_OTLP_ENDPOINT=ENDPOINT,
        OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=ENDPOINT+'/v1/logs',
        OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=ENDPOINT+'/v1/metrics',OTEL_EXPORTER_OTLP_TRACES_LIVE='1')
    for kind in ('CONFIG','DATA','STATE'):
        env['XDG_'+kind+'_HOME']=str(ROOT/'toolchain-cli-state'/kind.lower())
    def inspect():
        item=json.loads(subprocess.check_output(['docker','inspect',ENGINE],env=env,text=True))[0]
        return {key:item[key] for key in ('Id','Image','RestartCount')}
    before=inspect()
    assert before['Image']==IMAGE
    assert before['Id']=='d0d56f72a602d87b26fc32578569ece53b4536601423e3e5833edd284e6be097'
    argv=[sys.executable,str(ROOT/'test-toolchain-profiled.py'),'--dagger',str(CLI),'--module-dir',str(ROOT/'candidate')]
    record=dict(status='running',scope=__doc__,argv=argv,start_ns=time.time_ns(),engine=before,
        parent=build['parent'],source_hashes={str(p):h for p,h in pins.items()},script_sha256=sha(__file__))
    def save():
        (ROOT/'toolchain-capture.json').write_text(json.dumps(record,indent=2)+'\n')
    save()
    raw=ROOT/'toolchain-telemetry.jsonl'
    assert not raw.exists()
    with (ROOT/'toolchain-receiver.log').open('xb') as receiver_log:
        receiver=subprocess.Popen([str(RECEIVER),'-addr','127.0.0.1:43231','-out',str(raw)],env=env,
            stdout=receiver_log,stderr=subprocess.STDOUT)
        record['receiver_pid']=receiver.pid
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(100):
                assert receiver.poll() is None
                try:
                    for path in ('/v1/traces','/v1/logs','/v1/metrics'):
                        with opener.open(ENDPOINT+path,timeout=1) as response:
                            assert response.status==200
                    break
                except OSError:
                    if attempt==99: raise
                    time.sleep(.05)
            with (ROOT/'toolchain-run.log').open('xb') as log:
                result=subprocess.run(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            record['exit_code']=result.returncode
            roots=[line for line in (ROOT/'toolchain-run.log').read_text().splitlines()
                if line.startswith('/tmp/dagger-rust-toolchain-test-') and ' ' not in line]
            assert len(roots)==1
            record['root']=roots[0]
            assert result.returncode==0,'retain failed correctness sequence'
            assert json.loads((Path(roots[0])/'result.json').read_text())['passed']
            assert all(sha(path)==expected for path,expected in pins.items())
            assert inspect()==before
            record['status']='passed'
        except BaseException as error:
            record.update(status='failed',error=repr(error))
            raise
        finally:
            receiver.terminate()
            try: receiver.wait(timeout=10)
            except subprocess.TimeoutExpired: receiver.kill(); receiver.wait()
            record.update(receiver_exit_code=receiver.returncode,end_ns=time.time_ns())
            if raw.exists():
                record.update(telemetry_bytes=raw.stat().st_size,telemetry_sha256=sha(raw))
            save()
    print(json.dumps(record,indent=2))

if __name__=='__main__':
    main()
