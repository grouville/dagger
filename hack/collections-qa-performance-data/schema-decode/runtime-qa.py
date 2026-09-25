from pathlib import Path
import os,shutil,subprocess,json
os.environ.pop('SSH_AUTH_SOCK',None)
b=Path('/tmp/collections-perf/schema-decode');root=b/'runtime-qa';root.mkdir(exist_ok=True)
fixtures=Path('/home/dagger/dag/core/integration/testdata/modules/dang')
for name in ['self-calls','enum-dependency','test-interface','module-entrypoint']:
 dest=root/name
 if not dest.exists():shutil.copytree(fixtures/name,dest)
ws=root/'entrypoint-workspace';(ws/'tiny/entrypoint').mkdir(parents=True,exist_ok=True)
shutil.copyfile(root/'module-entrypoint/main.dang',ws/'tiny/entrypoint/main.dang')
(ws/'dagger.toml').write_text('[modules.tiny]\nsource = "tiny"\n')
(ws/'tiny/dagger-module.toml').write_text('name = "tiny"\n[entrypoint]\nkind = "dang"\nsource = "entrypoint"\n')
cases=[('self-calls',['fresh','get-message'],'hello from field'),('self-calls',['self-message'],'hello from field'),('self-calls',['widget','--label','constructed via api','get-label'],'constructed via api'),('self-calls',['widget-label','--label','constructed via api'],'constructed via api'),('enum-dependency',['call-foo'],'P256'),('test-interface',['local'],'hey, local'),('test-interface',['run'],'hi, world'),('entrypoint-workspace',['-m','tiny','hello'],'hello')]
rows=[]
for i,(fixture,args,want) in enumerate(cases):
 for name,engine in [('control','dagger-engine.collections-public-refs'),('candidate','dagger-engine.collections-schema-decode')]:
  cmd=['/tmp/collections-perf/committed/dagger','--engine','container://'+engine,'api','call',*args]
  p=subprocess.run(cmd,cwd=root/fixture,capture_output=True,text=True,timeout=120)
  (root/f'{i}-{name}.out').write_text(p.stdout);(root/f'{i}-{name}.err').write_text(p.stderr)
  correct=p.returncode==0 and p.stdout.strip()==want
  row={'fixture':fixture,'args':args,'variant':name,'status':p.returncode,'expected':want,'correct':correct};rows.append(row)
  (root/'summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
  assert correct,p.stderr[-2500:]
