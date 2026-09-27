from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
H=Path(__file__).resolve().parent;R=Path('/home/dagger/dag');GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';MOD='/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod'
p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');a=p.parse_args()
pattern='^Test(GlobHostPathCancellation|SearchHostPathNestedGitRepo|SearchWithRipgrepNoFilesSearched|FileStreamExportReplacesAtomically|ParentDirectoryMetadata.*|SessionAttachables.*)$'
cmds=[{'name':'baseline-existing','argv':[GO,'test','-mod=readonly','-modfile='+MOD,'-count=1','-timeout=90s','-run',pattern,'./engine/client']}]
for race in [False,True]:
 for pkg,pat in [('engine/session/attachables','^Test(GlobHostPathCancellation|SearchHostPathNestedGitRepo|SearchWithRipgrepNoFilesSearched|FileStreamExportReplacesAtomically|ParentDirectoryMetadata.*|ExtractedSocketProvider.*)$'),('engine/client','^Test(SessionAttachables.*|AttachablesPublicAliases)$')]:
  cmds.append({'name':('race-'if race else'normal-')+pkg.rsplit('/',1)[-1],'argv':[GO,'test','-mod=readonly','-modfile='+MOD,'-overlay='+str(H/'test-overlay.json'),*(['-race']if race else[]),'-count=1','-timeout=90s','-run',pat,'./'+pkg]})
if not a.run:print(json.dumps({'execute':False,'commands':cmds,'engine_calls':0,'cloud_calls':0}));raise SystemExit
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();m=json.loads((H/'manifest.json').read_text())
for rel,want in m['originals'].items():assert sha(R/rel)==want,rel
for path,want in m['sources'].items():assert sha(path)==want,path
out=H/'validation-v1';out.mkdir(exist_ok=False)
newdir=R/'engine/session/attachables';assert not newdir.exists(),'temporary package directory unexpectedly exists';newdir.mkdir()
env={k:os.environ[k]for k in ['PATH','HOME','USER','LOGNAME','TMPDIR']if k in os.environ};env.update(GOMAXPROCS='4',GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOENV='off',GOFLAGS='',CGO_ENABLED='1',GOOS='linux',GOARCH='amd64',DO_NOT_TRACK='1')
rows=[];data={'manifest_sha256':sha(H/'manifest.json'),'driver_sha256':sha(__file__),'source_head':m['head'],'checkout_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'modfile_sha256':sha(MOD),'modsum_sha256':sha(Path(MOD).with_suffix('.sum')),'environment':env,'engine_calls':0,'cloud_calls':0,'results':rows}
try:
 for item in cmds:
  t=time.monotonic();log=out/(item['name']+'.log')
  with log.open('wb')as f:
   result=subprocess.run(item['argv'],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
  rows.append({**item,'exit_code':result.returncode,'seconds':time.monotonic()-t,'log_sha256':sha(log)})
  (out/'results.json').write_text(json.dumps(data,indent=2)+'\n')
  print(json.dumps(rows[-1]),flush=True)
  assert result.returncode==0,item['name']
finally:
 newdir.rmdir();data['empty_package_dir_removed']=not newdir.exists();(out/'results.json').write_text(json.dumps(data,indent=2)+'\n')
