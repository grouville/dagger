import hashlib,json,os,pathlib,subprocess,time
P=pathlib.Path('/tmp/collections-perf/ancestor-request-v1');B=P/'builds';R=pathlib.Path('/home/dagger/dag')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
recipe=json.loads((B/'build-recipe.json').read_text());assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==recipe['source_head']
changed=subprocess.check_output(['git','diff','--name-only'],cwd=R,text=True).splitlines();assert all(x.startswith('hack/') for x in changed),changed
for p,h in recipe['inputs'].items():assert sha(p)==h,p
for v in recipe['originals'].values():assert sha(v['path'])==v['sha256']
results=[];env=os.environ|recipe['environment']
for name,argv in recipe['commands'].items():
 start=time.monotonic()
 with (B/('build-'+name+'.log')).open('w') as log:proc=subprocess.run(argv,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT)
 row={'name':name,'argv':argv,'exit_code':proc.returncode,'seconds':time.monotonic()-start}
 if proc.returncode==0:row.update(path=str(B/name),sha256=sha(B/name))
 results.append(row);(B/'build-results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(json.dumps(row),flush=True)
 if proc.returncode:raise SystemExit(proc.returncode)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==recipe['source_head']
by={v['name']:v for v in results}
manifest={'source_head':recipe['source_head'],'recipe_sha256':sha(B/'build-recipe.json'),'variants':{'baseline':{'cli':recipe['originals']['cli'],'engine':{k:by['engine-baseline'][k] for k in ['path','sha256']}},'candidate':{'cli':{k:by['cli-candidate'][k] for k in ['path','sha256']},'engine':{k:by['engine-candidate'][k] for k in ['path','sha256']}}},'wcprof_marker':'filesync.syncParentDirs','production_cloud_calls':0,'comparison':recipe['comparison']}
(B/'runtime-builds.json').write_text(json.dumps(manifest,indent=2)+'\n')
