#!/usr/bin/env python3
"""36 LOCAL clone-engine checks. Prepared only until root grants this exact driver.

Four ABBA blocks on one retained volume, same restored greetings path, fixed
baseAddress module and original CLI. Two exact listing primers before each block.
Ordinary observations n2/arm; unique comments/generation are not identical-byte
cache states. Two selected-Go failure/recovery pairs and profiles are separate.
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
 'selected':['check','--generated=false','go/modules/tests/run','--go-module=.','--go-test=TestFormatResponse'],
 'generate':['-y','generate','render']}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(b):return[b' '.join(v.split())for v in ANSI.sub(b'',b).splitlines()if v.strip()]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');a=p.parse_args()
 if not a.run:
  print(json.dumps({'execute':False,'local_cli_cap':CAP,'cloud_commands':0,'order':['baseline','candidate','candidate','baseline'],'block_calls':28,'separate_selected_failure_recovery':4,'diagnostic_primer_and_profiles':4,'ordinary_n_per_arm_per_flow':2,'same_existing_app_path':str(APP),'flows':FLOWS}));return
 frozen=json.loads((HERE/'frozen-runtime-inputs.json').read_text())
 for path,want in frozen['source_sha256'].items():assert sha(path)==want,'frozen source changed: '+path
 roots={'app':APP,'native':NATIVE};initial={k:x.fixture_hashes(v)for k,v in roots.items()}
 assert initial==frozen['fixtures']
 assert initial['app']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
 assert not(HERE/'summary-v1.json').exists()
 module=Path(frozen['module_path']);assert sha(module)==MODULE_SHA
 originals={k:{name:(root/name).read_bytes()if(root/name).exists()else None for name in names}for k,root,names in [('app',APP,('dagger.toml','dagger.lock','main.go','main_test.go')),('native',NATIVE,('input.txt','generated.txt','dagger.lock'))]}
 local=APP/'.dagger/perf-go';assert not local.exists()
 config=originals['app']['dagger.toml'];remote=b'source = "github.com/dagger/go@collections"';base=b'base = "dag://backend/go-test-base"'
 assert config.count(remote)==config.count(base)==1
 expected={k:x.fixture_hashes(v)for k,v in roots.items()};wanted=norm(Path(frozen['checks_golden']).read_bytes());assert len(wanted)==14
 golden=None;nonce=uuid.uuid4().hex;rows=[];locks=[];written=0
 facts={'local_cli_cap':CAP,'cloud_commands':0,'validated_commands':0,'scope':'Only in-place schema clone delta; identical flush/readiness instrumentation and ordinary init both engines. Four correlated ABBA blocks, n2 observations per arm/flow; no distribution, fresh-volume cold, service-up or Cloud claim. Native render is authored Changeset generation, not SDK code generation. Selected check uses normal chosen-test path with generated checks disabled deliberately.','source_delta':'Same historical6a82 behavior and optional baseAddress module; no narrow telemetry barrier, scheduling, socket or shared-transport candidate.'}
 def put(k,name,body):
  path=roots[k]/name
  if body is None:path.unlink(missing_ok=True);expected[k].pop(name,None)
  else:
   if not path.exists()or path.read_bytes()!=body:path.write_bytes(body)
   expected[k][name]=sha(path)
 def reset():
  for name in ('main.go','main_test.go'):put('app',name,originals['app'][name])
  put('native','input.txt',originals['native']['input.txt'])
  put('native','generated.txt',originals['native']['input.txt'])
 def guard():
  assert written<8*1024**3 and shutil.disk_usage(HERE).free>16*1024**3
  for k,root in roots.items():assert{k:v for k,v in x.fixture_hashes(root).items()if k!='dagger.lock'}=={k:v for k,v in expected[k].items()if k!='dagger.lock'},'fixture mutation: '+k
  assert all(sha(LAB/'greetings'/name)==want for name,want in initial['app'].items()),'original public fixture changed'
 def run(engine,variant,flow,phase,block,profile=False):
  nonlocal golden,written
  assert len(rows)<CAP;reset();target=contents=None;marker=None
  if phase=='fresh-comment':put('app','main.go',originals['app']['main.go']+f'\n// clone-{nonce}-{variant[0]}-{block:02d}\n'.encode())
  if phase=='negative':
   needle=b'func TestFormatResponse(t *testing.T) {';assert originals['app']['main_test.go'].count(needle)==1
   marker=f'clone-check-sentinel-{nonce}-{variant[0]}'.encode()
   put('app','main_test.go',originals['app']['main_test.go'].replace(needle,needle+b'\n\tt.Fatal("'+marker+b'")',1))
  if flow=='generate':
   contents=f'clone-generate-{nonce}-{variant[0]}-{block:02d}\n'.encode();put('native','input.txt',contents);put('native','generated.txt',None);target=NATIVE/'generated.txt'
  guard()
  def validate(row,stdout,stderr):
   nonlocal golden
   text=ANSI.sub(b'',stdout+b'\n'+stderr)
   if flow=='selected':
    identity=b'go/modules/tests/run'in text and b'TestFormatResponse'in text
    if phase=='negative':return row['exit_code']!=0 and identity and marker in text and re.search(rb'\b1 failed\b',text)is not None
    return row['exit_code']==0 and identity and re.search(rb'\b1 passed\b',text)is not None and re.search(rb'\b[1-9][0-9]* (failed|skipped)\b',text)is None and b'SKIP'not in text
   if row['exit_code']!=0:return False
   if flow=='checks':return norm(stdout)==wanted
   if flow=='artifacts':
    if not nav.known_listing(flow,stdout):return False
    if golden is None:assert variant=='baseline';golden=norm(stdout)
    return norm(stdout)==golden
   if flow=='generate':return target.exists()and target.read_bytes()==contents
   raise AssertionError(flow)
  row,stdout,stderr=engine.run(FLOWS[flow],NATIVE if flow=='generate'else APP,validate,f'{block:02d}-{variant}-{phase}-{flow}',profile=profile,timeout=300,output_path=target,expected_bytes=contents)
  if target is not None:expected['native'][target.name]=sha(target)
  row=dict(row,variant=variant,flow=flow,phase=phase,block=block,global_index=len(rows),app_main_sha256=sha(APP/'main.go'),app_test_sha256=sha(APP/'main_test.go'),native_input_sha256=sha(NATIVE/'input.txt'))
  rows.append(row);written+=row['engine_written_bytes'];locks.append({'index':row['global_index'],'app':sha(APP/'dagger.lock'),'native':sha(NATIVE/'dagger.lock')});x.write(HERE/'results-numeric.json',rows);guard()
 try:
  local.mkdir(parents=True)
  put('app','.dagger/perf-go/go.dang',module.read_bytes())
  put('app','.dagger/perf-go/dagger-module.toml',(HERE/'module-manifest.toml').read_bytes())
  put('app','dagger.toml',config.replace(remote,b'source = ".dagger/perf-go"').replace(base,b'baseAddress = "dag://backend/go-test-base"'))
  for block,variant in enumerate(('baseline','candidate','candidate','baseline')):
   reset();guard();extra=2 if block<2 else 0
   with EngineLifecycle(HERE/f'block-{block}',7+extra,variant)as engine:
    run(engine,variant,'checks','primer',block);run(engine,variant,'artifacts','primer',block)
    run(engine,variant,'checks','warm',block);run(engine,variant,'artifacts','warm',block)
    run(engine,variant,'selected','execution-control',block)
    run(engine,variant,'checks','fresh-comment',block)
    run(engine,variant,'generate','fresh-input',block)
    if extra:
     run(engine,variant,'selected','negative',block);run(engine,variant,'selected','restored',block)
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
  facts['original_public_fixture_untouched']=all(sha(LAB/'greetings'/name)==want for name,want in initial['app'].items())
  facts['ordinary_lock_hashes']=locks;facts['measured_command_engine_write_bytes']=written;facts['write_scope']='CLI-bracketing deltas, excludes provisioning/startup and gaps';x.write(HERE/'summary-v1.json',facts)
  assert all(facts['fixtures_restored'].values())and facts['original_public_fixture_untouched']
if __name__=='__main__':main()
