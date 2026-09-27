"""Prepared 16-command LOCAL correctness gate for Go SDK #36, backend only.

No latency comparison. Four counted generation calls; twelve API/list/check calls.
No engine call occurs without --run and the separately reviewed lifecycle helper.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tomllib
HERE=Path(__file__).resolve().parent
LAB=Path('/tmp/collections-perf/engine-allocation-round2')
APP=LAB/'greetings'
INPUT=LAB/'withfile-v1/prepared.json'
VALID=Path('/tmp/collections-perf/go-sdk-pr36-validation-v1')
SDK=VALID/'source'
EXPECTED=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt')
CAP=16
BACKEND=Path('.dagger/modules/backend')
EXPORTED=('New','Build','Binary','Container','Serve','GoTestBase')
MARKER='static-sdk-explicit-source-20260926'
SENTINEL='sdk36-intentional-fresh-failure'
METHOD='AddedAfterGenerate'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
normal=lambda n:re.sub('[^a-z0-9]','',n.lower())
ANSI=re.compile(rb'\x1b\[[0-9;]*[A-Za-z]')
def listing_lines(value):return [b' '.join(line.split())for line in ANSI.sub(b'',value).splitlines()if line.strip()]

def dump(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def content(result,key):
 value=result.get(key)
 if isinstance(value,bytes):return value
 if isinstance(value,str):return value.encode()
 return Path(result[key+'_path']).read_bytes()
def good(result):return result.get('exit_code',result.get('returncode'))==0

def scoped_config(source):
 return ('[modules.dagger-go-sdk]\nsource = '+json.dumps(source)+'\n'
  '[sdks.go]\nmodule = "dagger-go-sdk"\n'
  '[sdks.go.scopes.".dagger/modules/backend"]\nis-module = true\n').encode()

def annotate(text):
 for name in EXPORTED:
  # Use a literal assertion and replacement, retaining every authored body.
  target='func New(' if name=='New' else 'func (b *Backend) '+name+'('
  assert text.count(target)==1,(name,'missing/ambiguous declaration')
  pos=text.index(target)
  assert '+cache='not in text[max(0,pos-160):pos],('unexpected preexisting policy',name)
  text=text[:pos]+'// +cache="session"\n'+text[pos:]
 return text

PROBE='''package PACKAGE
import (
 "context"
 "encoding/json"
)
// +cache="session"
func (b *Backend) StaticTransportProbe(ctx context.Context, value string, values []string, count int,
 // +optional
 optional *string,
) (string, error) {
 marker, err := b.Source.File("sdk36-source-marker.txt").Contents(ctx)
 if err != nil { return "", err }
 body, err := json.Marshal(struct { Value string; Values []string; Count int; Optional *string; Marker string }{value, values, count, optional, marker})
 return string(body), err
}
'''
ADDED='''package PACKAGE
// +cache="session"
func (b *Backend) AddedAfterGenerate() string { return "fresh-api" }
'''
APPTEST='''package main
import (
 "net/http"
 "os"
 "strings"
 "testing"
)
func TestStaticSDKFreshApp(t *testing.T) {
 if os.Getenv("GREETINGS_API_URL") == "" { t.Fatal("sdk36-missing-api-url") }
 resp, body := get(t, "/foooooo", nil)
 if resp.StatusCode != http.StatusBadRequest || !strings.Contains(string(body), "no greeting found") { t.Fatalf("sdk36-bad-http-response: %d %s", resp.StatusCode, body) }
 FAIL_LINE
}
'''

def api_document(include_probe=False,include_added=False):
 text='{ moduleSource(refString: ".dagger/modules/backend") { asModule { objects { asObject { name functions { name } } } } }'
 if include_probe:
  text+=' backend { staticTransportProbe(value: '+json.dumps('hello "world"\n')+', values: ["x", "é"], count: 9007199254740993, optional: null) }'
 if include_added:text+=' backend { addedAfterGenerate }'
 return text+' }\n'

def methods(data):
 objs=data['moduleSource']['asModule']['objects']
 matches=[x['asObject']for x in objs if x.get('asObject') and normal(x['asObject']['name']).endswith('backend')]
 assert len(matches)==1,matches
 return sorted(normal(f['name'])for f in matches[0]['functions'])

def assert_policy(root,variant,added=False):
 module=root/BACKEND
 if variant=='control':
  config=tomllib.loads((module/'dagger-module.toml').read_text());assert config['disableDefaultFunctionCaching'] is True
  assert 'entrypoint'not in config
  text=(module/'dagger.gen.go').read_text()
  assert text.count('WithCachePolicy(dagger.FunctionCachePolicyPerSession)')==7+int(added),'wrong generated control policy count'
 else:
  config=tomllib.loads((module/'dagger-module.toml').read_text());assert config['manifestVersion']==2
  assert config['entrypoint']=={'kind':'dang','source':'./internal/dagger/entrypoint'}
  assert 'dependencies'not in config
  text=(module/'internal/dagger/entrypoint/main.dang').read_text()
  assert text.count('.withCachePolicy(FunctionCachePolicy.PerSession)')==7+int(added),'wrong generated candidate policy count'
  assert 'fnArgs: JSON!'in text and 'result :: JSON!'in text
 return {'manifest_sha256':sha(module/'dagger-module.toml'),'declarations_sha256':hashlib.sha256(text.encode()).hexdigest(),'session_policy_count':7+int(added)}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true');parser.add_argument('--output',default='results-v1');args=parser.parse_args()
 assert re.fullmatch(r'results-v[0-9]+',args.output)
 if not args.run:
  print(json.dumps({'execute':False,'total_cli_cap':CAP,'normal_generation_calls':4,'api_list_check_calls':12,'cloud_calls':0,'engine':'frozen ec6','cli':'frozen d685','scope':'backend-only, original greetings dependency loader unchanged','freshness':'current TOML and v2 before/after normal generation; live application test failure/recovery separately'}));return
 from lifecycle import EngineLifecycle
 os.umask(0o077);out=HERE/args.output;engine_out=HERE/(args.output+'-engine');assert not out.exists()and not engine_out.exists();out.mkdir()
 validation=json.loads((VALID/'validation.json').read_text());assert len(validation['results'])==5 and all(x['exit_code']==0 for x in validation['results'])
 assert validation['recipe_sha256']==sha(VALID/'recipe.json')
 provenance=json.loads((VALID/'source-provenance.json').read_text())
 assert provenance['commit']=='4dfd447d58344835a0d4692ec0c8e5683c18bd6f'
 for item in provenance['changed_files']:assert sha(SDK/item['path'])==item['candidate_sha256']
 git=lambda *argv:subprocess.check_output(['git','-C',str(SDK),*argv],timeout=15).decode().strip()
 assert git('rev-parse','HEAD')==provenance['commit']
 changed=set(git('diff','--name-only').splitlines())|set(git('ls-files','--others','--exclude-standard').splitlines())
 assert changed=={item['path']for item in provenance['changed_files']},'SDK checkout changed after validation'
 expected=json.loads(INPUT.read_text())['input_sha256']
 for path,digest in expected.items():assert sha(APP/path)==digest and not (APP/path).is_symlink()
 full_config=(APP/'dagger.toml').read_bytes();sdk_source=tomllib.loads(full_config.decode())['modules']['dagger-go-sdk']['source']
 roots={variant:out/variant for variant in ('control','candidate')}
 for variant,root in roots.items():
  root.mkdir()
  for path in expected:
   target=root/path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(APP/path,target)
  mainfile=root/BACKEND/'main.go';text=annotate(mainfile.read_text());assert text.startswith('package main\n')
  if variant=='candidate':text=text.replace('package main\n','package backend\n',1)
  mainfile.write_text(text)
  (root/BACKEND/'sdk36_probe.go').write_text(PROBE.replace('PACKAGE','main'if variant=='control'else'backend'))
  (root/'sdk36-source-marker.txt').write_text(MARKER)
  subprocess.run(['git','-c','core.hooksPath=/dev/null','init','-q',str(root)],check=True,timeout=15)
  subprocess.run(['git','-C',str(root),'-c','core.hooksPath=/dev/null','add','-f','.'],check=True,timeout=15)
 states={};freshness={};calls=[]
 dump(out/'provenance.json',{'driver_sha256':sha(__file__),'lifecycle_sha256':sha(HERE/'lifecycle.py'),'sdk_validation_sha256':sha(VALID/'validation.json'),'sdk_source':provenance,'input_manifest_sha256':sha(INPUT),'original_fixture_hashes':expected,'cap':CAP,'cloud_calls':0,'purpose':'correctness only; no timing performance comparison','generations_counted_separately':4,'engine_evidence_directory':str(engine_out)})
 def persist():dump(out/'workflow.json',{'calls':calls,'states':states,'freshness':freshness})
 try:
  with EngineLifecycle(engine_out,max_calls=CAP) as engine:
   def run(variant,label,argv,validator,timeout=120):
    calls.append({'ordinal':len(calls),'variant':variant,'label':label,'generation':label.startswith('generate')});persist()
    assert len(calls)<=CAP
    def wrapped(row,stdout,stderr):
     return validator(dict(row,stdout=stdout,stderr=stderr))
    row,stdout,stderr=engine.run(argv,cwd=roots[variant],validator=wrapped,label=variant+'-'+label,timeout=timeout)
    return dict(row,stdout=stdout,stderr=stderr)
   def generate(variant,label,added=False):
    root=roots[variant];path=root/'dagger.toml';assert path.read_bytes()==full_config
    path.write_bytes(scoped_config(sdk_source if variant=='control'else str(SDK)))
    try:run(variant,label,['-y','generate','dagger-go-sdk/generate'],good,timeout=300)
    finally:path.write_bytes(full_config)
    states[variant+'-'+label]=assert_policy(root,variant,added);persist()
   def api(variant,label,probe=False,added=False,observe=False):
    doc=out/(variant+'-'+label+'.graphql');doc.write_text(api_document(probe,added))
    result_holder={}
    def validate(result):
     if not good(result):
      if observe:result_holder['status']='error';return True
      return False
     data=json.loads(content(result,'stdout'));names=methods(data)
     result_holder.update(status='success',methods=names,added_present=normal(METHOD)in names)
     if added and normal(METHOD)not in names:return False
     if probe:
      value=json.loads(data['backend']['staticTransportProbe'])
      if value!={'Value':'hello "world"\n','Values':['x','é'],'Count':9007199254740993,'Optional':None,'Marker':MARKER}:return False
     if added and data['backend']['addedAfterGenerate']!='fresh-api':return False
     return True
    run(variant,label,['api','query','--doc',str(doc)],validate)
    states[variant+'-'+label]=result_holder;persist();return result_holder
   for variant in roots:
    generate(variant,'generate-initial')
    api(variant,'initial-api-and-json',probe=True)
   assert states['control-initial-api-and-json']['methods']==states['candidate-initial-api-and-json']['methods']
   want=EXPECTED.read_bytes();assert len(want.splitlines())==14
   for variant in roots:run(variant,'full-check-list',['check','-l','--all'],lambda result:good(result)and listing_lines(content(result,'stdout'))==listing_lines(want))
   for variant,root in roots.items():
    (root/BACKEND/'sdk36_added.go').write_text(ADDED.replace('PACKAGE','main'if variant=='control'else'backend'))
    freshness[variant]=api(variant,'new-api-without-generate',observe=True)
   for variant in roots:
    generate(variant,'generate-new-api',added=True)
    api(variant,'new-api-after-generate',added=True)
   for failing in (True,False):
    for variant,root in roots.items():
     test=root/'sdk36_fresh_test.go'
     test.write_text(APPTEST.replace('FAIL_LINE','t.Fatal("'+SENTINEL+'")'if failing else'// Fresh recovery; retain the strict HTTP assertion above.'))
     def check(result,failing=failing):
      combined=ANSI.sub(b'',content(result,'stdout')+b'\n'+content(result,'stderr'))
      identity=b'dag://go/modules/tests/run?go-module=.&go-test=TestStaticSDKFreshApp'
      if identity not in combined:return False
      return ((not good(result))and SENTINEL.encode()in combined and re.search(rb'\b1 failed\b',combined)is not None)if failing else(good(result)and re.search(rb'\b1 passed\b',combined)is not None and re.search(rb'\b[1-9][0-9]* failed\b',combined)is None)
     run(variant,'fresh-http-failure'if failing else'fresh-http-recovery',['check','go/modules/tests/run','--go-module=.','--go-test=TestStaticSDKFreshApp'],check,timeout=300)
   assert len(calls)==CAP
 finally:
  for root in roots.values():
   (root/'dagger.toml').write_bytes(full_config);(root/'sdk36_fresh_test.go').unlink(missing_ok=True)
  untouched=all(sha(APP/path)==digest for path,digest in expected.items())
  dump(out/'restoration.json',{'original_fixture_untouched':untouched,'full_workspace_configs_restored':all((r/'dagger.toml').read_bytes()==full_config for r in roots.values()),'temporary_app_tests_removed':all(not(r/'sdk36_fresh_test.go').exists()for r in roots.values()),'trial_migration_and_added_api_retained_for_review':True,'attempted_calls':len(calls),'expected_calls':CAP,'cloud_calls':0})
  assert untouched
 persist();print(json.dumps({'complete':True,'calls':len(calls),'generations':4,'freshness':freshness,'cloud_calls':0}))
if __name__=='__main__':main()
