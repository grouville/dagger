#!/usr/bin/env python3
"""Local Docker exact-hit transport pilot; not native/cold/invalidation evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

BIN_DIR=Path(__file__).resolve().parent
ROOT=BIN_DIR/'pilot'
BASE=Path('/tmp/dagger-rust-current-main-engine.QepteZyL/engine-source/hack/bench-rust-loop')
RECEIVER=Path('/tmp/dagger-rust-perf-sprint.1qnbuQ9j/otlpdump')
ENGINE='dagger-engine.rust-fresh-qeptezyl'
IDENTITY='ff1caa52447eaf97c9b97b1d7b8765b3679bb956af1298821759dab0e29b6f1e sha256:3df4828f5969eef38ec13cf445e2eb1f161d0e7f2f16606a863fe30a27a44181 true'
ENDPOINT='http://127.0.0.1:43226'

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    assert sys.argv[1:]==['--execute']
    ROOT.mkdir()
    assert not (ROOT/'pilot.json').exists()
    env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','DAGGER_','_DAGGER_','_EXPERIMENTAL_DAGGER_','OTEL_'))}
    env.pop('DOCKER_CONTEXT',None)
    env.update(DO_NOT_TRACK='1',DNT='1',DAGGER_NO_NAG='1',DOCKER_HOST='unix:///var/run/docker.sock',DAGGER_ENGINE='container://'+ENGINE)
    for kind in ('CONFIG','CACHE','DATA','STATE'):env['XDG_'+kind+'_HOME']=str(ROOT/'cli-state'/kind.lower())
    inspect=['docker','inspect','--format','{{.Id}} {{.Image}} {{.State.Running}}',ENGINE]
    assert subprocess.check_output(inspect,env=env,text=True).strip()==IDENTITY
    subprocess.run(['sha256sum','--check',str(BIN_DIR/'binaries.sha256')],check=True,cwd=ROOT,env=env)
    assert sha(RECEIVER)=='f2aef556572da41578a0336248b4c6d1972b9d050df2622e57303555752f9b38'
    shutil.copytree('/tmp/dagger-client-ready-overlap.xfvJBun1/project',ROOT/'project',ignore=shutil.ignore_patterns('.git','target'))
    subprocess.run(['git','init','-q'],cwd=ROOT/'project',env=env,check=True)
    assert subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=ROOT/'project',env=env,text=True).strip()==str(ROOT/'project')
    frozen={str(p):sha(p) for p in (BIN_DIR/'dagger-control',BIN_DIR/'dagger-candidate',BASE/'compare-cli.py',BASE/'module/main.dang',Path(__file__))}
    record=dict(status='running',engine=IDENTITY,source_hashes=frozen,started_ns=time.time_ns(),runs=[])
    def save():(ROOT/'pilot.json').write_text(json.dumps(record,indent=2)+'\n')
    def compare(name,samples,profiled):
        command=[sys.executable,str(BASE/'compare-cli.py'),'--before',str(BIN_DIR/'dagger-control'),
            '--after',str(BIN_DIR/'dagger-candidate'),'--workdir',str(ROOT/'project'),'--samples',str(samples),'--']
        if profiled:command+=['--profile']
        command+=['check','rust:check']
        with (ROOT/(name+'.log')).open('xb') as log:
            result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
        roots=[s for s in (ROOT/(name+'.log')).read_text().splitlines() if s.startswith('/tmp/dagger-rust-cli-pair-') and ' ' not in s]
        assert len(roots)==1
        record['runs'].append(dict(name=name,root=roots[0],command=command,profiled=profiled,exit_code=result.returncode))
        save()
        assert result.returncode==0,'failed pilot retained: '+name
    save()
    receiver=None
    try:
        compare('unprofiled',12,False)
        env.update(OTEL_EXPORTER_OTLP_ENDPOINT=ENDPOINT,OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=ENDPOINT+'/v1/logs',
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=ENDPOINT+'/v1/metrics',OTEL_EXPORTER_OTLP_TRACES_LIVE='1')
        with (ROOT/'receiver.log').open('xb') as log:
            receiver=subprocess.Popen([str(RECEIVER),'-addr','127.0.0.1:43226','-out',str(ROOT/'telemetry.jsonl')],env=env,stdout=log,stderr=subprocess.STDOUT)
            record['receiver_pid']=receiver.pid;save()
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for i in range(100):
                assert receiver.poll() is None
                try:
                    for path in ('/v1/traces','/v1/logs','/v1/metrics'):
                        with opener.open(ENDPOINT+path,timeout=1) as response:assert response.status==200
                    break
                except OSError:
                    if i==99:raise
                    time.sleep(.05)
            compare('profiled',3,True)
        assert subprocess.check_output(inspect,env=env,text=True).strip()==IDENTITY
        assert frozen=={p:sha(p) for p in frozen}
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if receiver:
            receiver.terminate()
            try:receiver.wait(timeout=10)
            except subprocess.TimeoutExpired:receiver.kill();receiver.wait()
            record['receiver_exit_code']=receiver.returncode
        raw=ROOT/'telemetry.jsonl'
        if raw.exists():record.update(telemetry_sha256=sha(raw),telemetry_bytes=raw.stat().st_size)
        record['ended_ns']=time.time_ns();save()
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
