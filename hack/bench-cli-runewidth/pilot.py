#!/usr/bin/env python3
"""Runewidth upgrade: paired standalone CLI and novel-edit pilot.

Same retained engine, original f6e module, separate Cargo caches for each side.
Both fixtures are primed with control, identical source/flags/cache histories.
No listener or existing cache reset. All check runs export local OTLP; separate
profiled companion cohorts. Not cold/onboarding/native or artifact performance.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parent
BASE=Path('/tmp/dagger-parser-stats.I2WPGLrS/engine-source')
BENCH=BASE/'hack/bench-rust-loop'
A=Path('/tmp/dagger-http-preconnect-main.tRLouH4d/dagger-candidate')
B=ROOT/'dagger-candidate'
MODULE=Path('/tmp/dagger-rust-single-source.FwiNYoEd/control')
RECEIVER=Path('/tmp/dagger-rust-perf-sprint.1qnbuQ9j/otlpdump')
ENDPOINT='http://127.0.0.1:43237'
ENGINE='dagger-parser-stats-i2wpglrs-b'
IDENTITY='d0d56f72a602d87b26fc32578569ece53b4536601423e3e5833edd284e6be097 sha256:c057d7eed790760d88e4cffb0f540adb9e230823b81759c0e86eeaae49d141a0 true'
RUST='rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    assert sys.argv[1:]==['--execute']
    assert not (ROOT/'pilot.json').exists()
    pins={
        A:'23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270',
        B:'ff1ef25902a037b41e8b16372fcdb806c0cffdd1568a0b9ed75b4e1ef1631f51',
        RECEIVER:'f2aef556572da41578a0336248b4c6d1972b9d050df2622e57303555752f9b38',
        MODULE/'main.dang':'f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1',
        MODULE/'dagger-module.toml':'80ceb12a068bb2c86041ba35bdcb24edada8ae228b77450de2ce917caa2ec8e5',
    }
    assert all(sha(p)==v for p,v in pins.items())
    for path in (Path(__file__),ROOT/'compare-cli-edits.py',BENCH/'run.py',BENCH/'compare-cli.py',
                 BENCH/'fixtures/rust-toolchain-rustfmt.toml',ROOT/'source/go.mod',ROOT/'source/go.sum'):
        pins[path]=sha(path)
    env={k:v for k,v in os.environ.items() if not k.startswith(('GIT_','DAGGER_','_DAGGER_','_EXPERIMENTAL_DAGGER_','OTEL_'))}
    env.pop('DOCKER_CONTEXT',None)
    env.pop('GODEBUG',None)
    env.update(DO_NOT_TRACK='1',DNT='1',DOCKER_HOST='unix:///var/run/docker.sock',DAGGER_ENGINE='container://'+ENGINE)
    for kind in ('CONFIG','CACHE','DATA','STATE'):
        env['XDG_'+kind+'_HOME']=str(ROOT/'cli-state'/kind.lower())
    inspect=['docker','inspect','--format','{{.Id}} {{.Image}} {{.State.Running}}',ENGINE]
    assert subprocess.check_output(inspect,env=env,text=True).strip()==IDENTITY
    address=subprocess.check_output(['docker','inspect',ENGINE,'--format',
        '{{.NetworkSettings.Networks.bridge.IPAddress}}'],env=env,text=True).strip()
    assert address.startswith('172.17.') and all(part.isdigit() for part in address.split('.'))
    record=dict(status='running',scope=__doc__,source_hashes={str(p):v for p,v in pins.items()},
        engine=IDENTITY,started_ns=time.time_ns(),runs=[],primers={})
    def save():
        (ROOT/'pilot.json').write_text(json.dumps(record,indent=2)+'\n')
    def run(label,argv,prefix):
        with (ROOT/(label+'.log')).open('xb') as log:
            result=subprocess.run(argv,cwd=BASE,env=env,stdout=log,stderr=subprocess.STDOUT)
        roots=[line for line in (ROOT/(label+'.log')).read_text().splitlines()
               if line.startswith(prefix) and ' ' not in line]
        record['runs'].append(dict(name=label,argv=argv,roots=roots,exit_code=result.returncode))
        save()
        assert result.returncode==0,(label,'failed; retained')
        assert len(roots)==1,(label,roots)
        return Path(roots[0])
    receiver=None
    save()
    try:
        # This measures complete no-engine startup, separately from Rust commands.
        run('version', [sys.executable,str(BENCH/'compare-cli.py'),'--before',str(A),'--after',str(B),
            '--workdir',str(ROOT),'--samples','20','--','version'],'/tmp/dagger-rust-cli-pair-')
        env.update(OTEL_EXPORTER_OTLP_ENDPOINT=ENDPOINT,
            OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=ENDPOINT+'/v1/logs',
            OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=ENDPOINT+'/v1/metrics',OTEL_EXPORTER_OTLP_TRACES_LIVE='1')
        with (ROOT/'receiver.log').open('xb') as log:
            receiver=subprocess.Popen([str(RECEIVER),'-addr','127.0.0.1:43237','-out',str(ROOT/'telemetry.jsonl')],
                env=env,stdout=log,stderr=subprocess.STDOUT)
        record['receiver_pid']=receiver.pid
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for attempt in range(100):
            assert receiver.poll() is None
            try:
                for path in ('/v1/traces','/v1/logs','/v1/metrics'):
                    with opener.open(ENDPOINT+path,timeout=1) as response:
                        assert response.status==200
                break
            except OSError:
                if attempt==99:raise
                time.sleep(.05)
        for side in ('before','after'):
            fixture=run('prime-'+side,[sys.executable,str(BENCH/'run.py'),'--dagger',str(A),
                '--module-dir',str(MODULE),'--image',RUST,'--samples','1',
                '--ripgrep','/tmp/dagger-rust-ripgrep-reference','--debug-url','http://'+address+':6060',
                '--pinned-source-sync','--prepare-project-toolchain',
                '--project-toolchain',str(BENCH/'fixtures/rust-toolchain-rustfmt.toml')],
                '/tmp/dagger-rust-loop-')
            record['primers'][side]=str(fixture)
            existing=subprocess.check_output(['docker','ps','-a','--filter',
                'name=^/rust-loop-'+fixture.name+'$','--format','{{.ID}}'],env=env,text=True).strip()
            assert not existing,'native primer container cleanup incomplete'
            save()
        before=Path(record['primers']['before'])/'dagger'
        after=Path(record['primers']['after'])/'dagger'
        for name,profile,samples in (('exact',False,12),('exact-profiled',True,3)):
            argv=[sys.executable,str(BENCH/'compare-cli.py'),'--before',str(A),'--after',str(B),
                '--before-workdir',str(before),'--after-workdir',str(after),'--samples',str(samples),'--']
            if profile:argv+=['--profile']
            argv+=['check','rust:check']
            run(name,argv,'/tmp/dagger-rust-cli-pair-')
        for name,profile,samples in (('edits',False,10),('edits-profiled',True,3)):
            argv=[sys.executable,str(ROOT/'compare-cli-edits.py'),'--dagger',str(A),'--after-dagger',str(B),
                '--before-workdir',str(before),'--after-workdir',str(after),'--samples',str(samples),'--execute']
            if profile:argv+=['--profile']
            run(name,argv,'/tmp/dagger-rust-module-edits-')
        assert subprocess.check_output(inspect,env=env,text=True).strip()==IDENTITY
        assert all(sha(p)==v for p,v in pins.items())
        record['status']='passed'
    except BaseException as error:
        record.update(status='failed',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        if receiver is not None:
            receiver.terminate()
            try:receiver.wait(timeout=10)
            except subprocess.TimeoutExpired:receiver.kill();receiver.wait()
            record['receiver_exit_code']=receiver.returncode
        raw=ROOT/'telemetry.jsonl'
        if raw.exists():
            record.update(telemetry_bytes=raw.stat().st_size,telemetry_sha256=sha(raw))
        record['finished_ns']=time.time_ns()
        save()
    print(json.dumps({k:record[k] for k in ('status','primers')},indent=2))

if __name__=='__main__':main()
