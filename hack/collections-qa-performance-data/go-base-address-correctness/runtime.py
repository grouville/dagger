#!/usr/bin/env python3
"""Prepared9-command LOCAL correctness proof; no timing comparison or Cloud."""
from pathlib import Path
import argparse, hashlib, json, re, shutil, subprocess, sys, tomllib
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from lifecycle import EngineLifecycle, ANSI
LAB=Path('/tmp/collections-perf/engine-allocation-round2')
APP=LAB/'greetings'
P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--run',action='store_true')
a=P.parse_args()
if not a.run:
    print(json.dumps({'run':False,'local_cli_cap':9,'retained_session_rpc_cap':10,'cloud_calls':0,'requires':'frozen-runtime-inputs.json + reviewed engine manifest','scope':'same-session cache classification + fresh-CLI edit/service correctness + original/candidate matched local Go module'}))
    raise SystemExit(0)
freeze=json.loads((HERE/'frozen-runtime-inputs.json').read_text())
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
for path,want in freeze['source_sha256'].items():assert sha(path)==want
control=Path(freeze['original_module']);candidate=Path(freeze['candidate_module'])
workspace=HERE/'workspace-v2';greetings=HERE/'greetings-v2';out=HERE/'results-v2'
assert not any(f.exists()for f in (workspace,greetings,out,HERE/'retained-result-v2.json'))
assert shutil.disk_usage(HERE).free>16*1024**3
subprocess.run([sys.executable,str(HERE/'prepare.py'),'--module-file',str(candidate),'--module-sha256',sha(candidate),'--workspace',str(workspace)],check=True,timeout=30)
inputs=json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
for name,want in inputs.items():assert sha(APP/name)==want
for name in inputs:
    dest=greetings/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(APP/name,dest)
subprocess.run(['git','init','-q',str(greetings)],check=True,timeout=10)
subprocess.run(['git','-C',str(greetings),'add','-f','.'],check=True,timeout=10)
gomod_manifest=(workspace/'.dagger/perf-go/dagger-module.toml').read_bytes()
local=greetings/'.dagger/perf-go';local.mkdir(parents=True)
(local/'dagger-module.toml').write_bytes(gomod_manifest)
original_config=(greetings/'dagger.toml').read_bytes()
assert original_config.count(b'source = "github.com/dagger/go@collections"')==1
local_config=original_config.replace(b'source = "github.com/dagger/go@collections"',b'source = ".dagger/perf-go"')
needle=b'base = "dag://backend/go-test-base"'
assert local_config.count(needle)==1
original_e2e=(greetings/'e2e_test.go').read_bytes()
assert original_e2e.count(b't.Skip("GREETINGS_API_URL')==1
strict_e2e=original_e2e.replace(b't.Skip("GREETINGS_API_URL',b't.Fatal("GREETINGS_API_URL')
(greetings/'e2e_test.go').write_bytes(strict_e2e)
expected_rows=[b' '.join(line.split())for line in Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes().splitlines()if line.strip()]
assert len(expected_rows)==14
synthetic_original={f:(workspace/f).read_bytes()for f in ('marker.txt','service-marker.txt','base_test.go')}
check=['check','go/modules/tests/run','--go-module=.','--go-test=TestBoundBase']
summary={'scope':'correctness only; all starts and first-use dependency work included but no performance inference','cloud_commands':0}
def check_validator(expected=None):
    def validate(row,stdout,stderr):
        text=ANSI.sub(b'',stdout+b'\n'+stderr)
        if expected:
            return row['exit_code']!=0 and expected in text and re.search(rb'\b1 failed\b',text) is not None
        return row['exit_code']==0 and re.search(rb'\b1 passed\b',text)is not None and re.search(rb'\b[1-9][0-9]* failed\b',text)is None and b'SKIP'not in text
    return validate
try:
    with EngineLifecycle(out,9)as engine:
        engine.run(['api','with-session','--load-workspace-modules',sys.executable,str(HERE/'probe.py'),'--workspace',str(workspace),'--output',str(HERE/'retained-result-v2.json')],workspace,lambda row,o,e:row['exit_code']==0,'retained-session',timeout=330)
        retained=json.loads((HERE/'retained-result-v2.json').read_text())
        assert retained['status']=='passed-with-retained-cache-classification'and retained['rpc_attempts']==10 and retained['restored']
        summary['retained_observations']=retained['observations']
        engine.run(check,workspace,check_validator(),'fresh-cli-original',timeout=300)
        (workspace/'service-marker.txt').write_text('wrong-service-marker\n')
        engine.run(check,workspace,check_validator(b'custom base service or generation mismatch'),'fresh-cli-wrong-service',timeout=300)
        (workspace/'service-marker.txt').write_bytes(synthetic_original['service-marker.txt'])
        test=synthetic_original['base_test.go'];assert test.count(b'// APP_EDIT_SENTINEL')==1
        (workspace/'base_test.go').write_bytes(test.replace(b'// APP_EDIT_SENTINEL',b't.Fatal("real-app-edit-sentinel")'))
        engine.run(check,workspace,check_validator(b'real-app-edit-sentinel'),'fresh-cli-edited-test',timeout=300)
        (workspace/'base_test.go').write_bytes(test)
        (workspace/'marker.txt').write_text('edited-marker\n');(workspace/'service-marker.txt').write_text('edited-marker\n')
        engine.run(check,workspace,check_validator(),'fresh-cli-recovered',timeout=300)
        for variant,module,config in [('control',control,local_config),('candidate',candidate,local_config.replace(needle,b'baseAddress = "dag://backend/go-test-base"'))]:
            (local/'go.dang').write_bytes(module.read_bytes());(greetings/'dagger.toml').write_bytes(config)
            cfg=tomllib.loads(config.decode());assert cfg['modules']['go']['source']=='.dagger/perf-go'
            assert cfg['modules']['go']['settings']=={('base'if variant=='control'else'baseAddress'):'dag://backend/go-test-base'}
            expected={str(f.relative_to(greetings)):sha(f)for f in greetings.rglob('*')if f.is_file()and'.git'not in f.relative_to(greetings).parts}
            def fixture_guard():
                actual={str(f.relative_to(greetings)):sha(f)for f in greetings.rglob('*')if f.is_file()and'.git'not in f.relative_to(greetings).parts}
                assert {k:v for k,v in actual.items()if k!='dagger.lock'}=={k:v for k,v in expected.items()if k!='dagger.lock'},'unexpected greetings mutation'
            def listing(row,stdout,stderr):
                lines=[b' '.join(line.split())for line in ANSI.sub(b'',stdout).splitlines()if line.strip()]
                return row['exit_code']==0 and lines==expected_rows
            engine.run(['check','-l','--all'],greetings,listing,variant+'-exact-list',timeout=180);fixture_guard()
            engine.run(['check','go/modules/tests/run','--go-module=.','--go-test=TestE2EUnknownLanguage'],greetings,check_validator(),variant+'-strict-http',timeout=300);fixture_guard()
        assert len(engine.rows)==9 and all(row['correct']for row in engine.rows)
        summary['validated_cli_commands']=9
finally:
    for f,body in synthetic_original.items():(workspace/f).write_bytes(body)
    (greetings/'dagger.toml').write_bytes(original_config);(greetings/'e2e_test.go').write_bytes(original_e2e)
    shutil.rmtree(local)
    summary['synthetic_restored']=all((workspace/f).read_bytes()==b for f,b in synthetic_original.items())
    summary['greetings_authored_source_restored']=all(sha(greetings/name)==want for name,want in inputs.items()if name!='dagger.lock')
    summary['original_greetings_untouched']=all(sha(APP/name)==want for name,want in inputs.items())
    summary['legitimate_copy_lock_sha256']=sha(greetings/'dagger.lock')
    (HERE/'summary-v2.json').write_text(json.dumps(summary,indent=2)+'\n')
