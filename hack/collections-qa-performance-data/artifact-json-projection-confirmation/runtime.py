#!/usr/bin/env python3
"""Prepared16 LOCAL artifact-only calls on the prior38 restored source path.
Four explicit primers followed by six alternating baseline/candidate pairs.
No new source path, file edit, profiles, Cloud, or engine/CLI build.
"""
from pathlib import Path
import argparse,hashlib,json,shutil
from lifecycle import EngineLifecycle,ANSI,x
P=Path(__file__).resolve().parent;PRIOR=P.parent/'runtime-v1';CAP=16

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(b):return[b' '.join(s.split())for s in ANSI.sub(b'',b).splitlines()if s.strip()]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');a=p.parse_args()
 if not a.run:print(json.dumps({'execute':False,'local_calls':16,'cloud_calls':0,'primers_per_cli':2,'warm_pairs':6,'profile_calls':0,'workspace':str(PRIOR/'greetings')}));return
 f=json.loads((P/'frozen-runtime-inputs.json').read_text())
 for path,want in f['source_sha256'].items():assert sha(path)==want,'frozen input changed: '+path
 prior=json.loads((PRIOR/'summary-v1.json').read_text());restore=json.loads((PRIOR/'results-v1/lifecycle-restoration.json').read_text())
 assert prior['validated_commands']==38 and all(prior['copied_fixtures_restored'].values())and all(prior['original_fixtures_untouched'].values())
 assert restore['validated_commands']==38 and not restore['cleanup_error_types']and all(restore[k]for k in('temporary_container_removed','original_engine_stopped','original_engine_binary_untouched','original_init_binary_untouched','retained_volume_preserved'))
 app=PRIOR/'greetings';initial=f['fixture_hashes'];assert x.fixture_hashes(app)==initial
 original_root=Path(f['original_fixture_root']);assert x.fixture_hashes(original_root)==initial
 local=app/'.dagger/perf-go';assert not local.exists();out=P/'results-v1';assert not out.exists()
 originals={name:(app/name).read_bytes()for name in ('dagger.toml','dagger.lock')};expected=dict(initial)
 config=originals['dagger.toml'];needle=b'source = "github.com/dagger/go@collections"';assert config.count(needle)==1
 config=config.replace(needle,b'source = ".dagger/perf-go"');needle=b'base = "dag://backend/go-test-base"';assert config.count(needle)==1
 config=config.replace(needle,b'baseAddress = "dag://backend/go-test-base"')
 golden=norm(Path(f['golden_path']).read_bytes());assert golden
 rows=[];facts={'scope':'Projection CLI artifact confirmation only, same restored prior source path and baseAddress module, n6 alternating pairs plus two primers per arm. No profiles, edits, Cloud, or cold claim.','cap':CAP,'cloud_commands':0}
 def guard():
  assert {k:v for k,v in x.fixture_hashes(app).items()if k!='dagger.lock'}=={k:v for k,v in expected.items()if k!='dagger.lock'}
  assert x.fixture_hashes(original_root)==initial
 def run(engine,variant,phase,index):
  guard()
  def validate(row,stdout,stderr):return row['exit_code']==0 and norm(stdout)==golden
  row,_,_=engine.run(['list','-a'],app,validate,f'{index:02d}-{variant}-{phase}-artifacts',cli_variant=variant,timeout=180)
  rows.append(dict(row,variant=variant,phase=phase,pair_index=index,module_sha256=sha(local/'go.dang'),config_sha256=sha(app/'dagger.toml')));x.write(P/'results-numeric.json',rows);guard()
 try:
  local.mkdir(parents=True);shutil.copyfile(P/'module-manifest.toml',local/'dagger-module.toml');shutil.copyfile(f['module_path'],local/'go.dang');(app/'dagger.toml').write_bytes(config)
  expected=x.fixture_hashes(app)
  assert sha(app/'dagger.toml')==f['configured_dagger_toml_sha256']and sha(local/'go.dang')==f['module_sha256']
  with EngineLifecycle(out,CAP)as engine:
   x.write(out/'comparison-provenance.json',{'frozen_inputs_sha256':sha(P/'frozen-runtime-inputs.json'),'scope':facts['scope'],'same_source_path_as_prior38':True,'same_engine_all_calls':True,'prior_golden_sha256':sha(f['golden_path']),'module_sha256':f['module_sha256'],'configured_dagger_toml_sha256':f['configured_dagger_toml_sha256'],'setup_excluded':'engine start and four counted primers; no preparatory Dagger calls'})
   for index,variant in enumerate(('baseline','candidate','candidate','baseline')):run(engine,variant,'primer',index)
   for index in range(6):
    for variant in (('baseline','candidate')if index%2==0 else('candidate','baseline')):run(engine,variant,'warm',index)
   assert len(rows)==CAP and all(row['correct']for row in rows);facts['validated_commands']=len(rows)
 finally:
  for name,body in originals.items():(app/name).write_bytes(body)
  if local.exists():shutil.rmtree(local)
  facts['prior_fixture_restored']=x.fixture_hashes(app)==initial;facts['original_fixture_untouched']=x.fixture_hashes(original_root)==initial
  x.write(P/'summary-v1.json',facts);assert facts['prior_fixture_restored']and facts['original_fixture_untouched']
if __name__=='__main__':main()
