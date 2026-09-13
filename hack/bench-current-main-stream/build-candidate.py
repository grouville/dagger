#!/usr/bin/env python3
"""Revalidate and build the input-first stream candidate; reuse the exact built A.

No cold timing in this controller. The failed original B and both negative
stages remain intact. Only one additional dependency production file differs.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE/'engine-source'
ORIGINAL = Path('/tmp/dagger-current-stream.17mx1Ldk')
HELPER = Path('/tmp/dagger-rust-current-main-engine.QepteZyL/build.py')
CLI = Path('/tmp/dagger-cli-runewidth.lhU4UO4i/dagger-candidate')
PARENT = '503d3410ef3df63fa6bc7a55c5c2453c4951c2c2'
MAIN = '7c35e6274737acff0f6bd76614abb5e04efa7d12'
NAME = 'dagger-stream-close-order-6u5eynjb'
DEP = 'internal/bench-image-stream/containerd/core/diff/apply/apply.go'
EXPECTED_CHANGES = {DEP, 'core/integration/engine_streamed_snapshot_test.go',
                    'engine/server/resolver/streamed_fetch_zstd_test.go'}
spec = importlib.util.spec_from_file_location('base', HELPER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def read(*argv,cwd=SOURCE):
    return subprocess.check_output(argv,cwd=cwd,env=base.environment(),text=True).strip()

def hashes(source):
    assert read('git','rev-parse','HEAD',cwd=source)==PARENT
    assert read('git','merge-base',MAIN,'HEAD',cwd=source)==MAIN
    assert not read('git','diff','--check',cwd=source)
    paths=set(read('git','diff','HEAD','--name-only',cwd=source).splitlines())
    paths.update(read('git','ls-files','--others','--exclude-standard',cwd=source).splitlines())
    return {p:sha(source/p) for p in sorted(paths)}

def inspect(name):
    item=json.loads(read('docker','inspect',name))[0]
    return {k:item[k] for k in ('Id','Image','State','RestartCount')}

def main():
    assert sys.argv[1:] in (['--plan'],['--execute'])
    assert sha(HELPER)=='6a56a60dfcefc3a5fe4460382b05dcf754cd7f8f632a862d1dd0018388b7ef4c'
    assert sha(CLI)=='ff1ef25902a037b41e8b16372fcdb806c0cffdd1568a0b9ed75b4e1ef1631f51'
    assert sha(base.BOOTSTRAP)==base.BOOTSTRAP_SHA
    previous=json.loads((ORIGINAL/'engine-builds/builds.json').read_text())
    assert previous['status']=='failed'
    assert previous['parent']==PARENT and previous['upstream_main']==MAIN
    a=next(b for b in previous['builds'] if b['side']=='A')
    assert a['status']=='built-and-query-passed'
    assert all(c['exit_code']==0 for c in a['commands'])
    frozen=hashes(SOURCE)
    old=previous['source_hashes']['B']
    assert set(frozen)==set(old)
    differences={p for p in frozen if frozen[p]!=old[p]}
    assert differences==EXPECTED_CHANGES,differences
    assert hashes(Path(a['source']))==previous['source_hashes']['A']
    # Accept only a real negative control and a passing identical-fixture fix.
    stages={label:json.loads((HERE/label/'stage.json').read_text())
            for label in ('gated-before','gated-after')}
    assert stages['gated-before']['status']=='failed'
    assert stages['gated-after']['status']=='passed'
    for label,stage in stages.items():
        assert stage['exit_code']==(1 if label=='gated-before' else 0)
    before=stages['gated-before']['source_hashes']
    after=stages['gated-after']['source_hashes']
    assert set(before)==set(after)
    assert {p for p in before if before[p]!=after[p]}=={DEP}
    assert all(sha(SOURCE/p)==h for p,h in after.items())
    root=HERE/'engine-builds'
    base.ROOT=root/'B'; base.REPO=SOURCE; base.SOURCE=SOURCE
    base.NAME=NAME; base.IMAGE='localhost/'+NAME
    plan=dict(status='planned',parent=PARENT,upstream_main=MAIN,scope=__doc__,
        original_failed_build=str(ORIGINAL/'engine-builds/builds.json'),
        original_failed_build_sha256=sha(ORIGINAL/'engine-builds/builds.json'),
        source_roots={'A':a['source'],'B':str(SOURCE)},
        source_hashes={'A':previous['source_hashes']['A'],'B':frozen},
        differences=previous['differences'],additional_changes=sorted(differences),
        controller_sha256=sha(__file__),builds=[a],
        stages={label:sha(HERE/label/'stage.json') for label in stages})
    if sys.argv[1:]==['--plan']:
        print(json.dumps({k:v for k,v in plan.items() if k not in ('source_hashes','builds')},indent=2));return
    assert read('docker','image','inspect',a['engine_after_smoke']['Image'],'--format','{{.Id}}')==a['engine_after_smoke']['Image']
    assert not read('docker','ps','-aq','--filter','name=^/'+NAME+'$')
    assert NAME not in read('docker','volume','ls','--format','{{.Name}}').splitlines()
    assert not read('docker','image','ls','--format','{{.Repository}}:{{.Tag}}',base.IMAGE)
    assert read('docker','image','inspect',base.PLACEHOLDER_IMAGE,'--format','{{.Id}}')==base.PLACEHOLDER_IMAGE
    (root/'B').mkdir(parents=True)
    retained=inspect('dagger-engine.rust-fresh-qeptezyl')
    item=dict(side='B',source=str(SOURCE),engine_name=NAME,commands=[],status='testing')
    plan['builds'].append(item);plan['status']='running'
    def save():
        (root/'builds.json').write_text(json.dumps(plan,indent=2)+'\n')
    def run(label,argv,stdin=None,extra_env=None):
        assert hashes(SOURCE)==frozen
        step=dict(label=label,argv=argv,start_ns=time.time_ns())
        item['commands'].append(step);save();print(label,flush=True)
        with (root/'B'/(label+'.log')).open('xb') as out:
            result=subprocess.run(argv,cwd=SOURCE,env=base.environment()|(extra_env or {}),
                input=stdin,text=True,stdout=out,stderr=subprocess.STDOUT)
        step.update(exit_code=result.returncode,end_ns=time.time_ns());save()
        assert result.returncode==0,label+' failed; retain source and logs'
    save()
    try:
        for label,pkg,pattern,race,count,timeout in (
            ('snapshot-race','./engine/snapshots','^(TestPipelinedApply|TestImportImage(Pipeline|Reuse|LayerReuse)|TestStreamedImport)',True,3,'90s'),
            ('gzip-private-race','./core/integration','^TestEngine$/^TestVerifiedStream(LargePrivateSnapshotRace|RealPrivateSnapshotRace)$',False,1,'5m'),
            ('zstd-private-race','./core/integration','^TestEngine$/^TestVerifiedStreamZstdRace$',False,1,'5m'),
        ):
            argv=[str(CLI),'api','call','engine-dev','test','--pkg='+pkg,'--run='+pattern,
                  '--parallel=1','--timeout='+timeout,'--count='+str(count),'--test-verbose=true']
            if race:argv.append('--race=true')
            run(label,argv,extra_env={'DAGGER_ENGINE':'container://dagger-engine.rust-fresh-qeptezyl'})
        run('placeholder-create',['docker','create','--name',NAME,'--label','dagger.rust.bench-owner='+HERE.name,base.PLACEHOLDER_IMAGE])
        item['placeholder']=inspect(NAME)
        assert item['placeholder']['State']['Status']=='created'
        assert read('docker','inspect','--format','{{index .Config.Labels "dagger.rust.bench-owner"}}',NAME)==HERE.name
        item['status']='building';save()
        run('engine-build',base.deploy_command())
        item['engine_after_build']=inspect(NAME)
        assert item['engine_after_build']['State']['Running']
        assert read('docker','image','inspect',base.IMAGE,'--format','{{.Id}}')==item['engine_after_build']['Image']
        run('smoke',[str(CLI),'api','query','--no-load-module'],stdin='{ __typename }\n',extra_env={'DAGGER_ENGINE':'container://'+NAME})
        item['engine_after_smoke']=inspect(NAME)
        assert item['engine_after_smoke']['Id']==item['engine_after_build']['Id']
        assert hashes(SOURCE)==frozen
        assert hashes(Path(a['source']))==previous['source_hashes']['A']
        now=inspect('dagger-engine.rust-fresh-qeptezyl')
        assert all(now[k]==retained[k] for k in ('Id','Image','RestartCount'))
        assert item['engine_after_smoke']['Image']!=a['engine_after_smoke']['Image']
        item['status']='built-and-query-passed';plan['status']='built-and-query-passed'
    except BaseException as error:
        plan.update(status='failed',error=repr(error));raise
    finally:
        plan['ended_ns']=time.time_ns();save()

if __name__=='__main__':main()
