#!/usr/bin/env python3
"""36 LOCAL observations of only the current-production registration snapshot.

ABBA blocks on one retained volume, same public fixture path, fixed baseAddress
module, original CLI and image init. No historical engine/source overlays.
Two core version probes, eight exact parity primers, eight warm listings, six
unique comment listings, four strict HTTP failure/recovery checks, four native generations, and
four final primer/profile calls. Stop at the first setup or semantic failure.
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, uuid
from lifecycle import EngineLifecycle, ANSI, x, nav
HERE=Path(__file__).resolve().parent
LAB=Path('/tmp/collections-perf/engine-allocation-round2')
APP=Path('/tmp/collections-perf/dang-admission-runtime-v1/greetings-v1')
NATIVE=LAB/'native'
CAP=36
MODULE_SHA='0b12a6f3fe091f5896c19f642e2074593dceca554275b150a450e06732d640be'
FLOWS={'checks':['check','-l','--all'],'artifacts':['list','-a'],
 'selected':['check','go/modules/tests/run','--go-module=.','--go-test=TestE2EUnknownLanguage'],
 'generate':['-y','generate','render'],'core':['-m','core','api','call','version']}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(b):return[b' '.join(v.split())for v in ANSI.sub(b'',b).splitlines()if v.strip()]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');a=p.parse_args()
 if not a.run:
  print(json.dumps({'execute':False,'local_cli_cap':CAP,'cloud_commands':0,'order':['baseline','candidate','candidate','baseline'],'core_version_probes':2,'parity_primers':8,'ordinary_n_per_arm_per_listing':2,'novel_comment_n_per_arm':3,'strict_http_failure_recovery_controls':4,'native_generate_controls':4,'diagnostic_primer_and_profiles':4,'same_existing_app_path':str(APP),'flows':FLOWS}));return
 frozen=json.loads((HERE/'frozen-runtime-inputs.json').read_text())
 for path,want in frozen['source_sha256'].items():assert sha(path)==want,'frozen source changed: '+path
 roots={'app':APP,'native':NATIVE};initial={k:x.fixture_hashes(v)for k,v in roots.items()}
 assert initial==frozen['fixtures']
 assert initial['app']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
 assert not(HERE/'summary-v1.json').exists()
 module=Path(frozen['module_path']);assert sha(module)==MODULE_SHA
 originals={k:{name:(root/name).read_bytes()if(root/name).exists()else None for name in names}for k,root,names in [('app',APP,('dagger.toml','dagger.lock','main.go','e2e_test.go')),('native',NATIVE,('input.txt','generated.txt','dagger.lock'))]}
 original_public=LAB/'greetings'
 assert all(sha(original_public/name)==want for name,want in initial['app'].items())
 local=APP/'.dagger/perf-go';assert not local.exists()
 expected={k:dict(v)for k,v in initial.items()};wanted=norm(Path(frozen['checks_golden']).read_bytes());assert len(wanted)==14
 golden=None;nonce=uuid.uuid4().hex;rows=[];locks=[];written=0
 facts={'local_cli_cap':CAP,'cloud_commands':0,'validated_commands':0,
  'scope':'Only the registration metadata snapshot differs between two current-production engines using ordinary go.mod. Both have identical SDK artifacts, baseAddress module, CLI and ordinary image init. ABBA n2 warm observations and n3 novel comments per arm. Profiles, version probes, selected checks and generation controls are separate from listing medians. No cold or Cloud claim.',
  'source_delta':'Current production control versus helpers.go + registration_metadata.go only. No historical core/Dang/SDK/telemetry source overlay, clone candidate or dependency replacement.',
  'native_generation_scope':'Authored Changeset generation, not SDK code generation.',
  'check_scope':'Normal selected-check UX with generated defaults. Missing service configuration is an error, never a skipped success.'}
 def put(k,name,body):
  path=roots[k]/name
  if body is None:path.unlink(missing_ok=True);expected[k].pop(name,None)
  else:
   if not path.exists()or path.read_bytes()!=body:path.write_bytes(body)
   expected[k][name]=sha(path)
 def reset():
  for name in ('main.go','e2e_test.go'):put('app',name,originals['app'][name])
  put('native','input.txt',originals['native']['input.txt'])
  put('native','generated.txt',originals['native']['input.txt'])
 def guard():
  assert written<8*1024**3 and shutil.disk_usage(HERE).free>16*1024**3
  for k,root in roots.items():assert{n:v for n,v in x.fixture_hashes(root).items()if n!='dagger.lock'}=={n:v for n,v in expected[k].items()if n!='dagger.lock'},'fixture mutation: '+k
  assert all(sha(original_public/name)==want for name,want in initial['app'].items()),'original public fixture changed'
 def run(engine,variant,flow,phase,block,profile=False):
  nonlocal golden,written
  assert len(rows)<CAP;reset();target=contents=marker=None
  if phase=='fresh-comment':put('app','main.go',originals['app']['main.go']+f'\n// registration-{nonce}-{variant[0]}-{block:02d}-{len(rows):02d}\n'.encode())
  if flow=='selected':
   needle=b't.Skip("GREETINGS_API_URL';assert originals['app']['e2e_test.go'].count(needle)==1
   strict=originals['app']['e2e_test.go'].replace(needle,b't.Fatal("GREETINGS_API_URL')
   if phase=='negative-control':
    marker=f'registration-http-sentinel-{nonce}-{variant[0]}'.encode()
    witness=b'assert.Assert(t, strings.Contains(string(body), "no greeting found for language \'foooooo\'"), "body: %s", body)'
    assert strict.count(witness)==1
    strict=strict.replace(witness,witness+b'\n\tt.Fatal("'+marker+b'")')
   put('app','e2e_test.go',strict)
  if flow=='generate':
   contents=f'registration-generate-{nonce}-{variant[0]}-{block:02d}\n'.encode();put('native','input.txt',contents);put('native','generated.txt',None);target=NATIVE/'generated.txt'
  guard()
  def validate(row,stdout,stderr):
   nonlocal golden
   text=ANSI.sub(b'',stdout+b'\n'+stderr)
   if flow=='selected':
    identity=b'go/modules/tests/run'in text and b'TestE2EUnknownLanguage'in text
    if phase=='negative-control':return row['exit_code']!=0 and identity and marker in text and re.search(rb'\b1 failed\b',text)is not None
    return row['exit_code']==0 and identity and re.search(rb'\b1 passed\b',text)is not None and re.search(rb'\b[1-9][0-9]* (failed|skipped)\b',text)is None and b'SKIP'not in text
   if row['exit_code']!=0:return False
   if flow=='core':return norm(stdout)==[engine.expected_version]
   if flow=='checks':return norm(stdout)==wanted
   if flow=='artifacts':
    if not nav.known_listing(flow,stdout):return False
    if golden is None:assert variant=='baseline';golden=norm(stdout)
    return norm(stdout)==golden
   if flow=='generate':return target.exists()and target.read_bytes()==contents
   raise AssertionError(flow)
  row,stdout,stderr=engine.run(FLOWS[flow],NATIVE if flow=='generate'else APP,validate,f'{block:02d}-{variant}-{phase}-{flow}',profile=profile,timeout=300,output_path=target,expected_bytes=contents)
  if target is not None:expected['native'][target.name]=sha(target)
  row=dict(row,variant=variant,flow=flow,phase=phase,block=block,global_index=len(rows),app_main_sha256=sha(APP/'main.go'),app_e2e_sha256=sha(APP/'e2e_test.go'),native_input_sha256=sha(NATIVE/'input.txt'))
  rows.append(row);written+=row['engine_written_bytes'];locks.append({'index':row['global_index'],'app':sha(APP/'dagger.lock'),'native':sha(NATIVE/'dagger.lock')});x.write(HERE/'results-numeric.json',rows);guard()
 try:
  local.mkdir(parents=True);put('app','.dagger/perf-go/go.dang',module.read_bytes());put('app','.dagger/perf-go/dagger-module.toml',(HERE/'module-manifest.toml').read_bytes())
  config=originals['app']['dagger.toml'];remote=b'source = "github.com/dagger/go@collections"';base=b'base = "dag://backend/go-test-base"'
  assert config.count(remote)==config.count(base)==1
  put('app','dagger.toml',config.replace(remote,b'source = ".dagger/perf-go"').replace(base,b'baseAddress = "dag://backend/go-test-base"'))
  for block,variant in enumerate(('baseline','candidate','candidate','baseline')):
   reset();guard()
   with EngineLifecycle(HERE/f'block-{block}',9 if block<2 else 7,variant)as engine:
    if block<2:run(engine,variant,'core','version-control',block)
    run(engine,variant,'checks','primer',block);run(engine,variant,'artifacts','primer',block)
    run(engine,variant,'checks','warm',block);run(engine,variant,'artifacts','warm',block)
    for _ in range(1 if block<2 else 2):run(engine,variant,'checks','fresh-comment',block)
    if block<2:
     run(engine,variant,'selected','negative-control',block);run(engine,variant,'selected','restored-control',block)
    run(engine,variant,'generate','fresh-input-control',block)
   facts['completed_blocks']=block+1;x.write(HERE/'progress.json',facts)
  for block,variant in enumerate(('baseline','candidate'),4):
   reset();guard()
   with EngineLifecycle(HERE/f'block-{block}',2,variant)as engine:
    run(engine,variant,'checks','diagnostic-primer',block);run(engine,variant,'checks','diagnostic',block,profile=True)
  assert len(rows)==CAP and all(r['correct']for r in rows);facts['validated_commands']=len(rows)
 finally:
  for k,files in originals.items():
   for name,body in files.items():
    path=roots[k]/name
    if body is None:path.unlink(missing_ok=True)
    else:path.write_bytes(body)
  if local.exists():shutil.rmtree(local)
  facts['fixtures_restored']={k:x.fixture_hashes(root)==initial[k]for k,root in roots.items()}
  facts['original_public_fixture_untouched']=all(sha(original_public/name)==want for name,want in initial['app'].items())
  facts['ordinary_lock_hashes']=locks;facts['measured_command_engine_write_bytes']=written;facts['write_scope']='CLI-bracketing deltas, excludes provisioning/startup and gaps';x.write(HERE/'summary-v1.json',facts)
  assert all(facts['fixtures_restored'].values())and facts['original_public_fixture_untouched']
if __name__=='__main__':main()
