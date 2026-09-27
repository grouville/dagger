from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent;ROOT=Path('/home/dagger/dag');GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';MOD='/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod'
p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');a=p.parse_args()
commands={v:[GO,'list','-mod=readonly','-modfile='+MOD,*(['-overlay='+str(HERE/'source-overlay.json')]if v=='candidate'else []),'-deps','-e','-json=ImportPath,Imports,GoFiles,Dir,Error,DepsErrors','./cmd/init']for v in ['baseline','candidate']}
if not a.run:print(json.dumps({'execute':False,'scope':'Go package metadata only; no compile/test/runtime or network','commands':commands}));raise SystemExit
out=HERE/'deps-v2';out.mkdir(exist_ok=False)
env=os.environ.copy();env.update(GOCACHE=str(HERE/'metadata-cache'),GOENV='off',GOFLAGS='',GOTOOLCHAIN='local',GOPROXY='off',GOSUMDB='off',GOMAXPROCS='2',CGO_ENABLED='0',GOOS='linux',GOARCH='amd64')
rows={};objects={}
for label,cmd in commands.items():
 t=time.monotonic();result=subprocess.run(cmd,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45);elapsed=time.monotonic()-t
 (out/(label+'.jsonstream')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
 values=[];text=result.stdout.decode();pos=0;decoder=json.JSONDecoder()
 while pos<len(text):
  while pos<len(text)and text[pos].isspace():pos+=1
  if pos==len(text):break
  value,pos=decoder.raw_decode(text,pos);values.append(value)
 objects[label]={v['ImportPath']:v for v in values};errors=[{'import':v['ImportPath'],'error':v['Error']}for v in values if v.get('Error')]
 rows[label]={'command':cmd,'exit_code':result.returncode,'metadata_seconds':elapsed,'packages':len(values),'errors':errors,'main_dependency_errors':values[-1].get('DepsErrors',[])if values else []}
removed=sorted(objects['baseline'].keys()-objects['candidate'].keys());added=sorted(objects['candidate'].keys()-objects['baseline'].keys())
(out/'summary.json').write_text(json.dumps({'scope':'static go-list metadata, not compiled or runtime-validated','runs':rows,'removed':removed,'added':added},indent=2)+'\n')
print(json.dumps({'baseline_packages':len(objects['baseline']),'candidate_packages':len(objects['candidate']),'removed':len(removed),'added':len(added),'exit_codes':{k:v['exit_code']for k,v in rows.items()},'errors':{k:len(v['errors'])for k,v in rows.items()}}))
