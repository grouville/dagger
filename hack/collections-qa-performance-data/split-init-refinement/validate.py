from pathlib import Path
import argparse, hashlib, json, os, subprocess, time
H=Path(__file__).resolve().parent
R=Path('/home/dagger/dag')
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
MOD='/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod'
p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--output',required=True);p.add_argument('--mounts-only',action='store_true');a=p.parse_args()
cmds=[]
for race in [False,True]:
 for pkg,pat in [('engine/session/initexec','^TestSplitInit'),('engine/engineutil','^TestSplitInitMounts$')]:
  cmds.append({'name':('race-'if race else'normal-')+pkg.rsplit('/',1)[-1],'argv':[GO,'test','-mod=readonly','-modfile='+MOD,'-overlay='+str(H/'overlay.json'),'-tags=dfexcludepatterns,dfparents',*(['-race']if race else[]),'-count=1','-v','-timeout=90s','-run',pat,'./'+pkg]})
cmds.append({'name':'compile-both-entrypoints','argv':[GO,'test','-mod=readonly','-modfile='+MOD,'-overlay='+str(H/'overlay.json'),'-tags=dfexcludepatterns,dfparents','-run=^$','./cmd/init','./cmd/init-lite']})
if a.mounts_only:cmds=[c for c in cmds if c['name'].endswith('-engineutil')]
if not a.run:
 print(json.dumps({'commands':cmds,'engine_calls':0,'cloud_calls':0}));raise SystemExit
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
m=json.loads((H/'manifest.json').read_text())
for rel,want in m['originals'].items():
 assert (sha(R/rel) if (R/rel).is_file() else None)==want,rel
for rel,want in m['sources'].items():assert sha(H/'source'/rel)==want,rel
out=H/a.output;assert out.parent==H;out.mkdir(exist_ok=False)
env={k:os.environ[k]for k in ['PATH','HOME','USER','LOGNAME','TMPDIR']if k in os.environ}
env.update(GOMAXPROCS='4',GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOENV='off',GOFLAGS='',CGO_ENABLED='1',GOOS='linux',GOARCH='amd64',DO_NOT_TRACK='1')
dirs=[R/'engine/session/initexec',R/'cmd/init-lite']
for d in dirs:assert not d.exists(),str(d)
data={'source_head':m['head'],'manifest_sha256':sha(H/'manifest.json'),'runner_sha256':sha(__file__),'modfile_sha256':sha(MOD),'modsum_sha256':sha(Path(MOD).with_suffix('.sum')),'environment':env,'engine_calls':0,'cloud_calls':0,'stages':[]}
created=[]
try:
 for d in dirs:d.mkdir();created.append(d)
 for item in cmds:
  start=time.monotonic();log=out/(item['name']+'.log')
  with log.open('wb')as f: proc=subprocess.run(item['argv'],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
  lines=log.read_text().splitlines()
  row={**item,'exit_code':proc.returncode,'seconds':time.monotonic()-start,'log_sha256':sha(log),'passed':[s for s in lines if s.lstrip().startswith('--- PASS:')],'skipped':[s for s in lines if s.lstrip().startswith('--- SKIP:')],'failed':[s for s in lines if s.lstrip().startswith('--- FAIL:')]}
  data['stages'].append(row);(out/'results.json').write_text(json.dumps(data,indent=2)+'\n')
  print(json.dumps({'name':row['name'],'exit_code':row['exit_code'],'seconds':row['seconds'],'passed':len(row['passed']),'failed':row['failed'],'skipped':row['skipped']}),flush=True)
  assert proc.returncode==0,item['name']
finally:
 for d in reversed(created):d.rmdir()
 data['temporary_dirs_removed']=all(not d.exists()for d in dirs)
 (out/'results.json').write_text(json.dumps(data,indent=2)+'\n')
