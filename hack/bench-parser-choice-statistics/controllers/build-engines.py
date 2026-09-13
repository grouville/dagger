#!/usr/bin/env python3
"""Build two current-main engine variants sequentially using supported dev flows.

Experimental local Dang replacement on both sides. The sole production
difference is generated choice-statistics bookkeeping, not image/CLI/cache logic.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
HELPER = Path('/tmp/dagger-rust-current-main-engine.QepteZyL/build.py')
CLI = Path('/tmp/dagger-http-preconnect-main.tRLouH4d/dagger-candidate')
MAIN = '7c35e6274737acff0f6bd76614abb5e04efa7d12'
PARENT = '503d3410ef3df63fa6bc7a55c5c2453c4951c2c2'
SOURCES = {'A':HERE/'engine-control', 'B':HERE/'engine-source'}
PREFIX = 'internal/bench-parser-stats/dang/'
spec = importlib.util.spec_from_file_location('base_build', HELPER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

def sha(path):
    with Path(path).open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()

def read(*argv, cwd=None):
    return subprocess.check_output(argv, cwd=cwd or HERE, env=base.environment(), text=True).strip()

def hashes(source):
    assert read('git','rev-parse','HEAD',cwd=source) == PARENT
    assert read('git','merge-base',MAIN,'HEAD',cwd=source) == MAIN
    changed = set(read('git','diff','HEAD','--name-only',cwd=source).splitlines())
    untracked = set(read('git','ls-files','--others','--exclude-standard',cwd=source).splitlines())
    assert changed == {'go.mod'}
    assert untracked and all(p.startswith(PREFIX) for p in untracked), untracked
    return {p:sha(source/p) for p in sorted(changed|untracked)}

def inspect(name):
    item = json.loads(read('docker','inspect',name))[0]
    return {k:item[k] for k in ('Id','Image','State','RestartCount')}

def main():
    assert sys.argv[1:] in (['--plan'], ['--execute'])
    assert sha(HELPER) == '6a56a60dfcefc3a5fe4460382b05dcf754cd7f8f632a862d1dd0018388b7ef4c'
    assert sha(CLI) == '23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270'
    assert sha(base.BOOTSTRAP) == base.BOOTSTRAP_SHA
    frozen = {side:hashes(source) for side,source in SOURCES.items()}
    assert set(frozen['A']) == set(frozen['B'])
    differences = [p for p in frozen['A'] if frozen['A'][p] != frozen['B'][p]]
    assert differences == [PREFIX+'pkg/dang/dang.peg.go'], differences
    assert frozen['A'][differences[0]] == sha(HERE/'control.dang.peg.go')
    assert frozen['B'][differences[0]] == sha(HERE/'dang/pkg/dang/dang.peg.go')
    plan = dict(upstream_main=MAIN,parent=PARENT,source_roots={k:str(v) for k,v in SOURCES.items()},
        differences=differences,source_hashes=frozen,scope=__doc__,script_sha256=sha(__file__))
    if sys.argv[1:] == ['--plan']:
        print(json.dumps({k:v for k,v in plan.items() if k!='source_hashes'},indent=2))
        return
    assert 'PASS' in (HERE/'dang-race-tests.log').read_text()
    assert (HERE/'pigeon-tests.log').read_text().count('ok  ') == 3
    assert json.loads((HERE/'parse-results.json').read_text())['favorable_pairs'] == 3
    root = HERE/'engine-builds'
    root.mkdir()
    plan.update(status='running',builds=[],validation_hashes={p:sha(HERE/p) for p in
        ('dang-race-tests.log','pigeon-tests.log','parse-results.json')})
    def save():
        (root/'builds.json').write_text(json.dumps(plan,indent=2)+'\n')
    save()
    retained = inspect('dagger-engine.rust-fresh-qeptezyl')
    try:
        for side in ('A','B'):
            source = SOURCES[side]
            output = root/side
            output.mkdir()
            name = 'dagger-parser-stats-i2wpglrs-'+side.lower()
            base.ROOT=output
            base.REPO=source
            base.SOURCE=source
            base.NAME=name
            base.IMAGE='localhost/'+name
            assert not read('docker','ps','-aq','--filter','name=^/'+name+'$')
            assert name not in read('docker','volume','ls','--format','{{.Name}}').splitlines()
            assert not read('docker','image','ls','--format','{{.Repository}}:{{.Tag}}',base.IMAGE)
            assert read('docker','image','inspect',base.PLACEHOLDER_IMAGE,'--format','{{.Id}}') == base.PLACEHOLDER_IMAGE
            item=dict(side=side,source=str(source),engine_name=name,commands=[],status='started')
            plan['builds'].append(item);save()
            def run(label,argv,stdin=None,extra_env=None):
                assert hashes(source)==frozen[side]
                entry=dict(label=label,argv=argv,start_ns=time.time_ns())
                item['commands'].append(entry);save()
                print(side,label,flush=True)
                with (output/(label+'.log')).open('x') as log:
                    p=subprocess.run(argv,cwd=source,env=base.environment()|(extra_env or {}),input=stdin,
                        text=True,stdout=log,stderr=subprocess.STDOUT)
                entry.update(exit_code=p.returncode,end_ns=time.time_ns());save()
                assert p.returncode==0,f'{side} {label} failed; keep exact logs'
            if side=='B':
                item['status']='integration-testing';save()
                run('dang-integration',[str(CLI),'api','call','engine-dev','test','--pkg=./core/integration',
                    '--run=^TestDang$/^Test(SelfCallReturningOwnType|Enums|Interfaces|Scalars|VersionedSyntax|CoreTypeShadowing|Directives|Mismatch)$',
                    '--parallel=1','--timeout=5m','--count=1','--test-verbose=true'],
                    extra_env={'DAGGER_ENGINE':'container://dagger-engine.rust-fresh-qeptezyl'})
            run('placeholder-create',['docker','create','--name',name,'--label',
                'dagger.rust.bench-owner='+HERE.name,base.PLACEHOLDER_IMAGE])
            item['placeholder']=inspect(name)
            assert item['placeholder']['State']['Status']=='created'
            assert read('docker','inspect','--format','{{index .Config.Labels "dagger.rust.bench-owner"}}',name)==HERE.name
            item['status']='building';save()
            run('engine-build',base.deploy_command())
            item['engine_after_build']=inspect(name);save()
            assert item['engine_after_build']['State']['Running']
            assert read('docker','image','inspect',base.IMAGE,'--format','{{.Id}}')==item['engine_after_build']['Image']
            run('smoke',[str(CLI),'api','query','--no-load-module'],stdin='{ __typename }\n',
                extra_env={'DAGGER_ENGINE':'container://'+name})
            item['engine_after_smoke']=inspect(name)
            assert item['engine_after_smoke']['Id']==item['engine_after_build']['Id']
            assert hashes(source)==frozen[side]
            item['status']='built-and-query-passed';save()
        now=inspect('dagger-engine.rust-fresh-qeptezyl')
        assert all(now[k]==retained[k] for k in ('Id','Image','RestartCount'))
        assert plan['builds'][0]['engine_after_smoke']['Image']!=plan['builds'][1]['engine_after_smoke']['Image']
        plan['status']='built-and-query-passed'
    except BaseException as error:
        plan.update(status='failed',error=repr(error))
        raise
    finally:
        plan['ended_ns']=time.time_ns();save()

if __name__=='__main__':
    main()
