from pathlib import Path
import hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent;REPO=Path('/home/dagger/dag');GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
base=[json.loads(l)for l in (HERE/'baseline.jsonl').read_text().splitlines()if l.startswith('{')];failed=[e['Test']for e in base if e.get('Action')=='fail'and e.get('Test')]
assert 'TestCurrentTypeDefsJSONWorkspaceDemand/__currentTypeDefsJSON' in failed
assert 'TestCurrentTypeDefsJSONAliasedRequestConsumesScope/__currentTypeDefsJSON' in failed
assert not any('/currentTypeDefs' in name for name in failed)
env=os.environ.copy();env.update(GOMAXPROCS='4',GOTOOLCHAIN='local',GOPROXY='off',CGO_ENABLED='1');rows=[]
regex='^(TestCurrentTypeDefsJSONWorkspaceDemand|TestCurrentTypeDefsJSONAliasedRequestConsumesScope|TestFilterPendingWorkspaceModulesForRootFields|TestFilterPendingWorkspaceModulesForScopedRootFields|TestEnsureRequestModulesLoadedConsumesScopeBeforeUnlock)$'
for race in (False,True):
 label='race'if race else'normal';cmd=[GO,'test','-json','-mod=readonly','-overlay='+str(HERE/'candidate-overlay.json')]+(['-race']if race else[])+['./engine/server','-run',regex,'-count=1'];log=HERE/(label+'.jsonl');assert not log.exists();started=time.monotonic()
 with log.open('w')as f:p=subprocess.run(cmd,cwd=REPO,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600)
 events=[json.loads(l)for l in log.read_text().splitlines()if l.startswith('{')];row={'label':label,'argv':cmd,'exit_code':p.returncode,'seconds':time.monotonic()-started,'passes':[e['Test']for e in events if e.get('Action')=='pass'and e.get('Test')],'failures':[e['Test']for e in events if e.get('Action')=='fail'and e.get('Test')],'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()};rows.append(row)
 (HERE/'validation.json').write_text(json.dumps({'baseline_expected_failures':failed,'baseline_log_sha256':hashlib.sha256((HERE/'baseline.jsonl').read_bytes()).hexdigest(),'candidate':rows},indent=2)+'\n');print(json.dumps({k:row[k]for k in ('label','exit_code','seconds','failures')}),flush=True)
 if p.returncode:raise SystemExit(p.returncode)
