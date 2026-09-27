"""Run only reviewed focused unit tests, a negative scheduler witness, then one engine build."""
from pathlib import Path
import hashlib,json,os,subprocess,time
D=Path(__file__).resolve().parent;R=Path('/home/dagger/dag')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
r=json.loads((D/'recipe.json').read_text());rh=sha(D/'recipe.json')
for p,h in r['inputs'].items():
 if sha(p)!=h:raise RuntimeError('input changed '+p)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==r['source_head']
results={'recipe_sha256':rh,'runner_sha256':sha(__file__),'steps':[],'engine_or_cloud_calls':0}
def run(label,cmd,env,negative=False):
 path=D/(label+'.log');start=time.monotonic()
 with path.open('wb')as out:code=subprocess.run(cmd,cwd=R,env={**os.environ,**env},stdout=out,stderr=subprocess.STDOUT,timeout=300).returncode
 elapsed=time.monotonic()-start
 text=path.read_text(errors='replace');events=[]
 for line in text.splitlines():
  try:events.append(json.loads(line))
  except json.JSONDecodeError:pass
 failed=[e['Test']for e in events if e.get('Action')=='fail'and e.get('Test')]
 passed=[e['Test']for e in events if e.get('Action')=='pass'and e.get('Test')]
 good=code==0
 if negative:good=code!=0 and failed==['TestModuleLoadPipelinePhaseBoundsAndOverlap'] and 'pipeline did not make expected progress'in text and 'pipeline cleanup failed'not in text and 'panic:'not in text
 step={'name':label,'command':cmd,'returncode':code,'wall_seconds':elapsed,'passed_tests':passed,'failed_tests':failed,'expected_negative':negative,'accepted':good,'log_sha256':sha(path)}
 results['steps'].append(step);save(D/'validation.json',results)
 print(json.dumps({k:step[k]for k in ['name','returncode','wall_seconds','accepted']}),flush=True)
 if not good:raise RuntimeError('validation failed: '+label)
run('normal',r['test_commands']['normal'],r['test_environments']['normal'])
run('race',r['test_commands']['race'],r['test_environments']['race'])
s=(D/'module_load_pipeline.go').read_text();assert '2*limit'in s
(D/'module_load_pipeline.negative.go').write_text(s.replace('2*limit','limit',1))
o=json.loads((D/'test-overlay.json').read_text());o['Replace'][str(R/'engine/server/module_load_pipeline.go')]=str(D/'module_load_pipeline.negative.go');save(D/'negative-overlay.json',o)
cmd=r['test_commands']['normal'][:];cmd=[('-overlay='+str(D/'negative-overlay.json'))if x.startswith('-overlay=')else x for x in cmd];cmd[cmd.index('-run')+1]='^TestModuleLoadPipelinePhaseBoundsAndOverlap$';cmd=[x.replace('-timeout=90s','-timeout=20s')for x in cmd]
run('negative-old-window',cmd,r['test_environments']['normal'],negative=True)
results['negative_inputs']={n:sha(D/n)for n in ['module_load_pipeline.negative.go','negative-overlay.json']};save(D/'validation.json',results)
run('build',r['build_command'],r['environment'])
binary=D/'engine-candidate';info=subprocess.check_output([r['build_command'][0],'version','-m',str(binary)],text=True)
settings={}
for line in info.splitlines():
 p=line.strip().split('\t')
 if len(p)==2 and p[0]=='build' and '='in p[1]:
  k,v=p[1].split('=',1)
  if k in ['vcs.revision','vcs.modified','vcs.time','GOOS','GOARCH','CGO_ENABLED']:settings[k]=v
assert settings['vcs.revision']==r['source_head']
v=subprocess.check_output(['git','show',r['source_head']+':internal/version/VERSION'],cwd=R,text=True).strip().removeprefix('v')
expected='v'+v+'+'+settings['vcs.revision'][:8]+('.dirty'if settings['vcs.modified']=='true'else'')
base=json.loads(Path(r['baseline_recipe']).with_name('manifest.json').read_text())
save(D/'manifest.json',{'source_head':r['source_head'],'recipe_sha256':rh,'validation_sha256':sha(D/'validation.json'),'baseline_engine':r['baseline_engine'],'candidate_engine':{'path':str(binary),'sha256':sha(binary)},'cli':base['cli'],'expected_core_version':expected,'engine_build_info':settings,'scope':r['scope'],'cloud_commands':0,'runtime_commands':0})
print(json.dumps({'manifest_sha256':sha(D/'manifest.json'),'candidate_sha256':sha(binary),'expected_core_version':expected}),flush=True)
