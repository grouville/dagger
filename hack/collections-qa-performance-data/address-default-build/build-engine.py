from pathlib import Path
import hashlib,json,os,subprocess,time,argparse
H=Path(__file__).resolve().parent;B=H/'builds';R=Path('/home/dagger/dag');A=argparse.ArgumentParser();A.add_argument('--run',action='store_true');args=A.parse_args()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
r=json.loads((B/'build-recipe.json').read_text());rh=sha(B/'build-recipe.json')
def verify():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==r['source_head']
 status=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=normal'],cwd=R,text=True).splitlines()
 assert all(any(line[3:].startswith(p)for p in r['allowed_dirty_prefixes'])for line in status),status
 for group in ('inputs','external_dependency_inputs','source_originals'):
  for p,h in r[group].items():assert sha(p)==h,'input changed: '+p
 assert sha(r['go']['path'])==r['go']['sha256']
 assert sha(H/'validation-v2/results.json')==r['validation_sha256']
 return status
status=verify()
if not args.run:print(json.dumps({'dry_run':True,'command':r['command'],'recipe_sha256':rh,'status':status}));raise SystemExit
assert not (B/'runtime-builds.json').exists(),'output already frozen'
started=time.monotonic();log=B/'build.private.log'
with log.open('wb')as f:p=subprocess.run(r['command'],cwd=R,env={**os.environ,**r['environment']},stdout=f,stderr=subprocess.STDOUT,timeout=300)
result={'recipe_sha256':rh,'runner_sha256':sha(__file__),'exit_code':p.returncode,'seconds':time.monotonic()-started,'log_sha256':sha(log),'preflight_status':status,'runtime_commands':0,'cloud_commands':0};save(B/'build-results.json',result)
assert p.returncode==0,'engine build failed'
verify();binary=B/'engine-address';info=subprocess.check_output([r['go']['path'],'version','-m',str(binary)],text=True);settings={}
for line in info.splitlines():
 fields=line.strip().split('\t')
 if len(fields)==2 and fields[0]=='build'and'='in fields[1]:
  k,v=fields[1].split('=',1)
  if k in ('vcs.revision','vcs.time','vcs.modified','GOOS','GOARCH','CGO_ENABLED'):settings[k]=v
assert settings['vcs.revision']==r['source_head']
version=(R/'internal/version/VERSION').read_text().strip().removeprefix('v');expected='v'+version+'+'+settings['vcs.revision'][:8]+('.dirty'if settings['vcs.modified']=='true'else'')
manifest={'engine':{'path':str(binary),'sha256':sha(binary),'exit_code':0},'expected_core_version':expected,'recipe_path':str(B/'build-recipe.json'),'recipe_sha256':rh,'build_results_sha256':sha(B/'build-results.json'),'source_head':r['source_head'],'behavior_source_head':r['behavior_source_head'],'baseline_ancestry_engine_sha256':r['baseline_ancestry_engine']['sha256'],'cli':r['cli'],'build_info':settings,'scope':r['scope'],'runtime_commands':0,'cloud_commands':0}
save(B/'runtime-builds.json',manifest);print(json.dumps(manifest),flush=True)
