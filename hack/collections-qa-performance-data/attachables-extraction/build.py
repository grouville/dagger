from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
H=Path(__file__).resolve().parent;R=Path('/home/dagger/dag');GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go';MOD='/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod'
p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');a=p.parse_args();out=H/'build-results-v1'
commands={v:[GO,'build','-mod=readonly','-modfile='+MOD,'-buildvcs=true',*(['-overlay='+str(H/'source-overlay.json')]if v=='candidate'else[]),'-tags=dfexcludepatterns,dfparents','-ldflags=-s -w','-o',str(out/('dagger-init-'+v)),'./cmd/init']for v in ['baseline','candidate']}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();m=json.loads((H/'manifest.json').read_text());env={k:os.environ[k]for k in ['PATH','HOME','USER','LOGNAME','TMPDIR']if k in os.environ};env.update(GOMAXPROCS='4',GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOENV='off',GOFLAGS='',CGO_ENABLED='0',GOOS='linux',GOARCH='amd64',GOAMD64='v1')
recipe={'source_head':m['head'],'checkout_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'manifest_sha256':sha(H/'manifest.json'),'modfile':MOD,'modfile_sha256':sha(MOD),'modsum_sha256':sha(Path(MOD).with_suffix('.sum')),'source_overlay_sha256':sha(H/'source-overlay.json'),'commands':commands,'environment':env,'scope':'matched original heavy helpers; no split-init alias/light binary or engine combination','engine_calls':0,'cloud_calls':0}
if not a.run:
 (H/'build-recipe.json').write_text(json.dumps(recipe,indent=2)+'\n');print(json.dumps(recipe));raise SystemExit
frozen=json.loads((H/'build-recipe.json').read_text());assert recipe==frozen,'recipe inputs or checkout changed'
for rel,want in m['originals'].items():assert sha(R/rel)==want,rel
for path,want in m['sources'].items():assert sha(path)==want,path
validation=json.loads((H/'validation-v1/results.json').read_text());assert len(validation['results'])==5 and all(x['exit_code']==0 for x in validation['results']) and validation['empty_package_dir_removed']
out.mkdir(exist_ok=False);data={'recipe_sha256':sha(H/'build-recipe.json'),'builds':{},'engine_calls':0,'cloud_calls':0}
for variant,cmd in commands.items():
 t=time.monotonic();log=out/(variant+'.log')
 with log.open('wb')as f:r=subprocess.run(cmd,cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
 binary=out/('dagger-init-'+variant);data['builds'][variant]={'path':str(binary),'sha256':sha(binary)if r.returncode==0 else None,'bytes':binary.stat().st_size if r.returncode==0 else None,'exit_code':r.returncode,'seconds':time.monotonic()-t,'command':cmd,'log_sha256':sha(log)}
 (out/'runtime-builds.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data['builds'][variant]),flush=True);assert r.returncode==0
