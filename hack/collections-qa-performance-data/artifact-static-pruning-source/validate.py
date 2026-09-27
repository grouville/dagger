from pathlib import Path
import hashlib,json,os,subprocess,time
P=Path(__file__).resolve().parent
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
MOD='/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod'
pattern='^(TestArtifactStatic.*|TestArtifactTypeDefinitionsStayStatic|TestArtifactItemsJSON|TestArtifactDirectiveFilterDoesNotRequireWorkspace)$'
rows=[]
for label,extra in [('normal',[]),('race',['-race'])]:
 cmd=[GO,'test',*extra,'-json','-mod=readonly','-modfile='+MOD,'-overlay='+str(P/'test-overlay.json'),'-count=1','-timeout=90s','-run',pattern,'./core/schema']
 start=time.monotonic()
 with (P/(label+'.log')).open('wb') as log:
  proc=subprocess.run(cmd,cwd='/home/dagger/dag',stdout=log,stderr=subprocess.STDOUT,timeout=240,env={**os.environ,'GOTOOLCHAIN':'local','GOPROXY':'off','GOSUMDB':'off'})
 events=[]
 for line in (P/(label+'.log')).read_text().splitlines():
  try: events.append(json.loads(line))
  except json.JSONDecodeError: pass
 row={'label':label,'command':cmd,'returncode':proc.returncode,'wall_seconds':time.monotonic()-start,'pass':[e['Test']for e in events if e.get('Action')=='pass'and 'Test'in e],'fail':[e['Test']for e in events if e.get('Action')=='fail'and 'Test'in e],'log_sha256':hashlib.sha256((P/(label+'.log')).read_bytes()).hexdigest()}
 rows.append(row);(P/'validation.json').write_text(json.dumps({'steps':rows,'engine_calls':0,'cloud_calls':0},indent=2)+'\n');print(json.dumps(row),flush=True)
 if proc.returncode:raise SystemExit(proc.returncode)
