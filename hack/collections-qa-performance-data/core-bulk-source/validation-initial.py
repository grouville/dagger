"""Run only the prepared local core metadata witnesses; no engine/Cloud workload."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
H=Path(__file__).resolve().parent;R=Path('/home/dagger/dag');GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
P=argparse.ArgumentParser();P.add_argument('--run',action='store_true');P.add_argument('--out',type=Path,default=H/'validation-v1');a=P.parse_args()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base='^TestCoreBulkPublicationUsesOneFinalUpdate$'
focused='^(TestCoreBulkPublicationMetadataOwnership|TestCoreBulkPublicationUsesOneFinalUpdate|TestBaseSchemaAllowlist|TestCoreSchemaTypeDefContentsAfterSessionRelease|TestCLITypeDefsJSONCoreParity|TestCurrentTypeDefsReturnAllTypesAfterSessionRelease)$'
commands=[]
for label,overlay,regex,race in [('baseline-witness','baseline-consumer-overlay.json',base,False),('candidate','test-overlay.json',focused,False),('candidate-race','test-overlay.json',focused,True)]:
 cmd=[GO,'test','-json','-mod=readonly','-overlay='+str(H/overlay)]
 if race:cmd.append('-race')
 cmd+=['./core/schema','-run',regex,'-count=1']
 commands.append({'label':label,'argv':cmd})
if not a.run:print(json.dumps({'execute':False,'commands':commands,'expected_baseline_failure':'Both functions=10 object/interface work witnesses; other subtests pass.','scope':'local focused package tests only, zero Cloud, no engine'}));raise SystemExit
assert not a.out.exists();a.out.mkdir()
provenance=json.loads((H/'source-provenance.json').read_text());assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==provenance['head']
for path,want in provenance['source'].items():assert sha(path)==want,path
for name,want in json.loads((H/'candidate-hashes.json').read_text()).items():assert sha(H/name)==want,name
(a.out/'validate.py.txt').write_bytes(Path(__file__).read_bytes());env=os.environ.copy();env.update(GOMAXPROCS='4',GOPROXY='off',GOTOOLCHAIN='local')
summary={'head':provenance['head'],'script_sha256':sha(__file__),'environment':{k:env[k]for k in ('GOMAXPROCS','GOPROXY','GOTOOLCHAIN')},'candidate_hashes':json.loads((H/'candidate-hashes.json').read_text()),'runs':[]}
for item in commands:
 log=a.out/(item['label']+'.jsonl');start=time.monotonic()
 with log.open('w')as f:result=subprocess.run(item['argv'],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
 events=[]
 for line in log.read_text().splitlines():
  try:events.append(json.loads(line))
  except json.JSONDecodeError:pass
 failures=[e['Test']for e in events if e.get('Action')=='fail'and 'Test'in e]
 passed=[e['Test']for e in events if e.get('Action')=='pass'and 'Test'in e]
 row={**item,'exit_code':result.returncode,'seconds':time.monotonic()-start,'failures':failures,'passes':passed,'log_sha256':sha(log)};summary['runs'].append(row)
 (a.out/'results.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:row[k]for k in ('label','exit_code','seconds','failures')}),flush=True)
 if item['label']=='baseline-witness':
  expected={'TestCoreBulkPublicationUsesOneFinalUpdate/functions=10/interface=false','TestCoreBulkPublicationUsesOneFinalUpdate/functions=10/interface=true','TestCoreBulkPublicationUsesOneFinalUpdate'}
  assert result.returncode!=0 and set(failures)==expected,failures
  assert all(any(p.endswith(x)for p in passed)for x in ['functions=0/interface=false','functions=0/interface=true','functions=1/interface=false','functions=1/interface=true'])
 else:assert result.returncode==0
summary['all_expected_results']=True;(a.out/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
