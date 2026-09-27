from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
ROOT=Path('/home/dagger/dag');HERE=Path(__file__).resolve().parent
GO=Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go')
MOD=Path('/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--output',default='validation-v1');args=p.parse_args()
manifest=json.loads((HERE/'manifest.json').read_text())
for name,want in manifest['sources'].items():
    kind,rel=name.split('/',1);actual=HERE/('source'if kind=='engine'else'module')/rel
    assert sha(actual)==want,(name,'candidate source changed')
for name,want in manifest['originals'].items():
    kind,rel=name.split('/',1)
    if kind=='engine' and want is not None:assert sha(ROOT/rel)==want,(name,'original source changed')
original=HERE/'original-modfunc.go'
if not original.exists():original.write_bytes((ROOT/'core/modfunc.go').read_bytes())
assert sha(original)==manifest['originals']['engine/core/modfunc.go']
overlay=json.loads((HERE/'test-overlay.json').read_text())
overlay['Replace'][str(ROOT/'core/modfunc.go')]=str(original)
(HERE/'baseline-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
base=[str(GO),'test','-mod=readonly','-modfile='+str(MOD),'-tags=dfexcludepatterns,dfparents','-count=1','-v','-timeout=120s']
cases=[('baseline-address-witness',base+['-overlay='+str(HERE/'baseline-overlay.json'),'-run','^TestUserDefaultAddress','./core'],False),('candidate-address',base+['-overlay='+str(HERE/'test-overlay.json'),'-run','^TestUserDefault(Address|WithoutDotEnv)','./core'],True),('candidate-address-race',base+['-race','-overlay='+str(HERE/'test-overlay.json'),'-run','^TestUserDefault(Address|WithoutDotEnv)','./core'],True),('module-parse',base+[str(HERE/'module_parse_test.go')],True)]
fixed={'PATH':str(GO.parent)+':/usr/bin:/bin','HOME':'/home/dagger','GOMAXPROCS':'4','GOPROXY':'off','GOSUMDB':'off','GOTOOLCHAIN':'local','GOENV':'off','GOFLAGS':'','CGO_ENABLED':'1','GOOS':'linux','GOARCH':'amd64','DO_NOT_TRACK':'1'}
record={'source_head':manifest['source_head'],'manifest_sha256':sha(HERE/'manifest.json'),'runner_sha256':sha(Path(__file__)),'go_sha256':sha(GO),'modfile_sha256':sha(MOD),'modsum_sha256':sha(MOD.with_suffix('.sum')),'environment':{k:v for k,v in fixed.items()if k not in ('PATH','HOME')},'engine_calls':0,'cloud_calls':0,'stages':[],'parser_input_sha256':{str(p):sha(p)for p in [HERE/'module_parse_test.go',HERE/'module/go.dang',HERE/'module/.dagger/modules/go-dev/main.dang',Path('/tmp/collections-perf/go-base-address-retained-v1/fixture/probe/main.dang')]}}
if not args.run:
    print(json.dumps({'stages':[{'name':n,'argv':cmd,'expected_success':good}for n,cmd,good in cases]},indent=2));raise SystemExit
out=HERE/args.output;out.mkdir(exist_ok=False)
try:
    for name,cmd,success in cases:
        started=time.time();log=out/(name+'.log')
        with log.open('wb')as f:result=subprocess.run(cmd,cwd=ROOT,env=fixed,stdout=f,stderr=subprocess.STDOUT,timeout=300)
        text=log.read_text();passed=result.returncode==0 if success else result.returncode!=0 and 'resolve object ("Address")'in text and '--- FAIL: TestUserDefaultAddress'in text and '[build failed]'not in text
        row={'name':name,'argv':cmd,'exit_code':result.returncode,'seconds':time.time()-started,'expected_success':success,'passed':passed,'log_sha256':sha(log)}
        record['stages'].append(row);(out/'results.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(row),flush=True)
        if not passed:raise SystemExit('stage did not satisfy expected gate: '+name)
finally:(out/'results.json').write_text(json.dumps(record,indent=2)+'\n')
