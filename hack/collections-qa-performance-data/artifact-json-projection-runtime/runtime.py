#!/usr/bin/env python3
"""38 LOCAL calls comparing only composed artifact JSON projection in the CLI.

Same retained Address engine, optional baseAddress module/configuration and path.
Six native correctness calls, six explicit listing primers, eighteen warm samples,
four first-seen app-comment listings, then four separate primer/profile calls.
No fresh-volume cold, Cloud, real Go execution performance or SDK codegen claim.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,uuid
from lifecycle import EngineLifecycle,ANSI,x,nav
HERE=Path(__file__).resolve().parent;LAB=Path('/tmp/collections-perf/engine-allocation-round2');CAP=38
FLOWS={'checks':['check','-l','--all'],'artifacts':['list','-a'],'generators':['generate','-l'],'native-ws':['ws','ls'],'native-generate':['-y','generate','render'],'native-check':['check']}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(b):return[b' '.join(v.split())for v in ANSI.sub(b'',b).splitlines()if v.strip()]
def copy_fixture(source,target,hashes):
 assert not target.exists()
 for name,want in hashes.items():
  assert sha(source/name)==want
  dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,dest)
 subprocess.run(['git','init','-q',str(target)],check=True,timeout=10)
 subprocess.run(['git','-C',str(target),'add','-f','.'],check=True,timeout=10)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');a=p.parse_args()
 if not a.run:
  print(json.dumps({'execute':False,'local_cli_cap':CAP,'cloud_calls':0,'native_correctness':6,'listing_primers':6,'warm_samples_per_flow_per_cli':3,'fresh_comment_listings_per_cli':2,'profile_primers':2,'profiles':2,'flows':FLOWS,'engine':'same frozen Address38711','module':'same fixed baseAddress candidate','source_effective':'historical d685 plus only projection in candidate'}));return
 frozen=json.loads((HERE/'frozen-runtime-inputs.json').read_text())
 for path,want in frozen['source_sha256'].items():assert sha(path)==want,'frozen source changed: '+path
 for label in ('app','native'):
  assert x.fixture_hashes(Path(frozen['original_fixture_roots'][label]))==frozen['original_fixtures'][label]
 initial=frozen['original_fixtures'];roots={'app':HERE/'greetings','native':HERE/'native'}
 for label,target in roots.items():copy_fixture(Path(frozen['original_fixture_roots'][label]),target,initial[label])
 app,native=roots['app'],roots['native'];out=HERE/'results-v1';assert not out.exists()
 app_original={name:(app/name).read_bytes()for name in ('dagger.toml','dagger.lock','main.go')}
 native_original={name:(native/name).read_bytes()if(native/name).exists()else None for name in ('input.txt','generated.txt','dagger.lock')}
 local=app/'.dagger/perf-go';assert not local.exists();local.mkdir(parents=True)
 shutil.copyfile(HERE/'module-manifest.toml',local/'dagger-module.toml');shutil.copyfile(frozen['module_path'],local/'go.dang')
 config=app_original['dagger.toml'];needle=b'source = "github.com/dagger/go@collections"';assert config.count(needle)==1
 config=config.replace(needle,b'source = ".dagger/perf-go"');needle=b'base = "dag://backend/go-test-base"';assert config.count(needle)==1
 (app/'dagger.toml').write_bytes(config.replace(needle,b'baseAddress = "dag://backend/go-test-base"'))
 expected={label:x.fixture_hashes(root)for label,root in roots.items()};wanted=norm(Path(frozen['expected_checks_path']).read_bytes());assert len(wanted)==14
 nonce=uuid.uuid4().hex;goldens={};rows=[];locks=[]
 def put(label,name,body):
  path=roots[label]/name
  if body is None:path.unlink(missing_ok=True);expected[label].pop(name,None)
  else:
   if not path.exists()or path.read_bytes()!=body:path.write_bytes(body)
   expected[label][name]=sha(path)
 def guard():
  for label,root in roots.items():
   assert {k:v for k,v in x.fixture_hashes(root).items()if k!='dagger.lock'}=={k:v for k,v in expected[label].items()if k!='dagger.lock'},'fixture mutation: '+label
   assert x.fixture_hashes(Path(frozen['original_fixture_roots'][label]))==initial[label],'original fixture changed'
 def reset_native():
  for name,body in native_original.items():put('native',name,body)
 def run(engine,variant,flow,phase,index,profile=False):
  put('app','main.go',app_original['main.go']);target=contents=None
  if phase=='fresh-comment':put('app','main.go',app_original['main.go']+f'\n// json-projection-{nonce}-{variant[0]}-{index:02d}\n'.encode())
  if flow=='native-generate':
   contents=f'json-native-{nonce}-{variant[0]}\n'.encode();put('native','input.txt',contents);put('native','generated.txt',None);target=native/'generated.txt'
  guard();input_sha=sha(app/'main.go')
  def validate(row,stdout,stderr):
   if row['exit_code']!=0:return False
   text=ANSI.sub(b'',stdout+b'\n'+stderr);lines=norm(stdout)
   if flow=='checks':return lines==wanted
   if flow in ('artifacts','generators'):
    if not nav.known_listing(flow,stdout):return False
   elif flow=='native-ws':
    if not all(entry in lines for entry in (b'input.txt',b'module/',b'dagger.toml')):return False
   elif flow=='native-generate':return target.exists()and target.read_bytes()==contents
   elif flow=='native-check':return bool(re.search(rb'\b[1-9][0-9]* passed\b',text))and b' failed'not in text and b' skipped'not in text
   else:raise AssertionError('unknown flow')
   if flow not in goldens:
    assert variant=='baseline','baseline must establish ordered golden';goldens[flow]=lines
   return lines==goldens[flow]
  row,stdout,stderr=engine.run(FLOWS[flow],native if flow.startswith('native-')else app,validate,f'{index:02d}-{variant}-{phase}-{flow}',cli_variant=variant,profile=profile,timeout=180,output_path=target,expected_bytes=contents)
  if target is not None:expected['native'][target.name]=sha(target)
  row=dict(row,variant=variant,flow=flow,phase=phase,pair_index=index,app_main_sha256=input_sha,module_sha256=sha(local/'go.dang'),config_sha256=sha(app/'dagger.toml'))
  rows.append(row);x.write(HERE/'results-numeric.json',rows);locks.append({'index':row['index'],'app_lock_sha256':sha(app/'dagger.lock'),'native_lock_sha256':sha(native/'dagger.lock')});guard()
 facts={'scope':'CLI JSON projection only. Same engine, fixed optional-baseAddress Go module, source path, init and dependencies. Warm n3 per flow/CLI; unique comment n2/CLI. Alternating order within each round, not a cold distribution. Native output/check smoke is correctness, not SDK codegen or Go-test benchmark. Profiles excluded from ordinary samples.','local_cli_cap':CAP,'cloud_commands':0}
 try:
  with EngineLifecycle(out,CAP)as engine:
   x.write(out/'comparison-provenance.json',{'frozen_inputs_sha256':sha(HERE/'frozen-runtime-inputs.json'),'cli_manifest_sha256':sha(HERE/'frozen-cli-manifest.json'),'engine_manifest_sha256':sha(HERE/'frozen-engine-manifest.json'),'same_engine_all_commands':True,'same_module_and_configuration_both_arms':True,'module_sha256':sha(local/'go.dang'),'config_sha256':sha(app/'dagger.toml'),'scope':facts['scope'],'profile_scope':'exact check-list primer immediately before same CLI profiled check-list, no engine restart','native_generation_boundary':'fresh never-evaluated bytes, actual generated.txt equality and 5ms visibility polling; no SDK generation','nonce_sha256':hashlib.sha256(nonce.encode()).hexdigest()})
   for variant in ('baseline','candidate'):
    reset_native()
    for flow in ('native-ws','native-generate','native-check'):run(engine,variant,flow,'correctness',0)
   reset_native()
   for variant in ('baseline','candidate'):
    for flow in ('checks','artifacts','generators'):run(engine,variant,flow,'primer',0)
   for index in range(3):
    order=('baseline','candidate')if index%2==0 else('candidate','baseline')
    for flow in ('checks','artifacts','generators'):
     for variant in order:run(engine,variant,flow,'warm',index)
   for index in range(2):
    for variant in (('baseline','candidate')if index%2==0 else('candidate','baseline')):run(engine,variant,'checks','fresh-comment',index)
   for index,variant in enumerate(('baseline','candidate')):
    run(engine,variant,'checks','diagnostic-primer',index);run(engine,variant,'checks','diagnostic',index,profile=True)
   assert len(rows)==CAP and all(row['correct']for row in rows);facts['validated_commands']=len(rows)
 finally:
  for name,body in app_original.items():(app/name).write_bytes(body)
  if local.exists():shutil.rmtree(local)
  for name,body in native_original.items():
   if body is None:(native/name).unlink(missing_ok=True)
   else:(native/name).write_bytes(body)
  facts['copied_fixtures_restored']={label:x.fixture_hashes(root)==initial[label]for label,root in roots.items()}
  facts['original_fixtures_untouched']={label:x.fixture_hashes(Path(frozen['original_fixture_roots'][label]))==initial[label]for label in roots}
  facts['ordinary_lock_hashes']=locks;x.write(HERE/'summary-v1.json',facts)
  assert all(facts['copied_fixtures_restored'].values())and all(facts['original_fixtures_untouched'].values())
if __name__=='__main__':main()
