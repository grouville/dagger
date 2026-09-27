"""Build three ordinary CLIs with one frozen source/dependency baseline."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,time
P=Path(__file__).resolve().parent;B=P.parent;R=Path('/home/dagger/dag');OUT=P/'builds';INPUT=OUT/'inputs'
HEAD='85b60f7a0a16a27459ef571bc94bcf870c876dcc'
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
ENGINE=Path('/tmp/collections-perf/sdk-edit-audit/root-demand-v1/engine-json-demand');ENGINE_SHA='9912b76324d1015e6811ea3a8ac7bdfb029ce6c079226c9a3b7aa6de8a3212a5'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v): Path(p).write_text(json.dumps(v,indent=2)+'\n')
def git(*args): return subprocess.check_output(['git',*args],cwd=R,text=True).strip()
def verify(recipe):
 assert git('rev-parse','HEAD')==recipe['source_head']
 assert not git('diff','--name-only','HEAD'),'Tracked source must remain clean'
 for name,digest in recipe['inputs'].items(): assert sha(name)==digest,name
 assert sha(GO)==recipe['toolchain_sha256'];assert sha(ENGINE)==ENGINE_SHA

def main():
 a=argparse.ArgumentParser();a.add_argument('--prepare',action='store_true');a.add_argument('--run',action='store_true');arg=a.parse_args();assert arg.prepare!=arg.run
 if arg.prepare:
  assert git('rev-parse','HEAD')==HEAD;assert not git('diff','--name-only','HEAD')
  INPUT.mkdir(parents=True,exist_ok=False)
  SDK=INPUT/'sdk-log-v016';OTEL=INPUT/'otel-go-pinned'
  shutil.copytree(P/'sdk-log-v016',SDK);shutil.copytree('/tmp/collections-perf/cli-exit-tail-v2/otel-go-pinned',OTEL)
  assert (OTEL/'init.go').read_bytes()==(B/'init.original.go').read_bytes(),'Original pinned Close changed'
  for f in ['batch.go','exporter.go']:
   assert (SDK/f).read_bytes()==(Path('/home/dagger/go/pkg/mod/go.opentelemetry.io/otel/sdk/log@v0.16.0')/f).read_bytes()
   shutil.copyfile(P/f,INPUT/('backport-'+f))
  shutil.copyfile(B/'init.go',INPUT/'overlap-init.go')
  mod=(P/'backport.mod').read_text().replace(str(P/'sdk-log-v016'),str(SDK)).replace('/tmp/collections-perf/cli-exit-tail-v2/otel-go-pinned',str(OTEL))
  (OUT/'cli.mod').write_text(mod);shutil.copyfile(P/'backport.sum',OUT/'cli.sum')
  repl={str(SDK/f):str(INPUT/('backport-'+f))for f in ['batch.go','exporter.go']}
  for name,mapping in [('baseline',{}),('queuefix',repl),('overlap',{**repl,str(OTEL/'init.go'):str(INPUT/'overlap-init.go')})]: save(OUT/(name+'-overlay.json'),{'Replace':mapping})
  env={'CGO_ENABLED':'0','GOOS':'linux','GOARCH':'amd64','GOAMD64':'v1','GOMAXPROCS':'4','GOPROXY':'off','GOTOOLCHAIN':'local'}
  cmds={name:[GO,'build','-mod=readonly','-modfile='+str(OUT/'cli.mod'),'-buildvcs=true','-overlay='+str(OUT/(name+'-overlay.json')),'-o',str(OUT/('dagger-'+name)),'./cmd/dagger']for name in ['baseline','queuefix','overlap']}
  inputs={str(p):sha(p)for p in sorted(INPUT.rglob('*'))if p.is_file()}
  for f in ['cli.mod','cli.sum','baseline-overlay.json','queuefix-overlay.json','overlap-overlay.json']: inputs[str(OUT/f)]=sha(OUT/f)
  recipe={'source_head':HEAD,'source_tree':git('rev-parse','HEAD^{tree}'),'tracked_changes':[],'toolchain':GO,'toolchain_sha256':sha(GO),'environment':env,'commands':cmds,'inputs':inputs,'engine':{'path':str(ENGINE),'sha256':ENGINE_SHA},'validation_manifest_sha256':sha(P/'manifest.json'),'scope':{'baseline':'Current committed source and unchanged v0.16 SDK/Close','queuefix':'Only the two backported worker/chunk-drain source files differ','overlap':'Queuefix plus joined early log ForceFlush before trace Shutdown'},'holds':'No diagnostic instrumentation, engine rebuild, dependency upgrade, daemon, background delivery, source metadata override or extra cache.'}
  save(OUT/'build-recipe.json',recipe);verify(recipe);print(OUT/'build-recipe.json');return
 recipe=json.loads((OUT/'build-recipe.json').read_text());verify(recipe)
 env=os.environ.copy();env.update(recipe['environment']);result={};manifest={'source_head':HEAD,'recipe_path':str(OUT/'build-recipe.json'),'recipe_sha256':sha(OUT/'build-recipe.json'),'variants':{},'engine':recipe['engine']}
 for name,cmd in recipe['commands'].items():
  verify(recipe);started=time.monotonic()
  with (OUT/(name+'-build.log')).open('w')as f:run=subprocess.run(cmd,cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=600)
  row={'exit_code':run.returncode,'build_seconds':time.monotonic()-started,'source_head':git('rev-parse','HEAD'),'command':cmd}
  if run.returncode==0:
   binary=OUT/('dagger-'+name);row.update(path=str(binary),sha256=sha(binary));manifest['variants'][name]={'path':str(binary),'sha256':row['sha256']}
  result[name]=row;save(OUT/'build-results.json',result);save(OUT/'manifest.json',manifest);print(json.dumps({'variant':name,**row}),flush=True)
  if run.returncode:raise SystemExit(run.returncode)
 verify(recipe);assert len(manifest['variants'])==3
if __name__=='__main__':main()
