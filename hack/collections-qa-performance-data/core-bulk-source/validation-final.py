"""Exact final isolated tests, with import grouping and independent alias/error witnesses."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
HERE=Path(__file__).resolve().parent; ROOT=Path('/home/dagger/dag')
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
PATTERN='^(TestCoreBulkPublicationMetadataOwnership|TestCoreBulkPublicationUsesOneFinalUpdate|TestCoreBulkPublicationAliasReplacement|TestCoreBulkPublicationInvalidIDPreservesReceiver|TestBaseSchemaAllowlist|TestCoreSchemaTypeDefContentsAfterSessionRelease|TestCLITypeDefsJSONCoreParity|TestCurrentTypeDefsReturnAllTypesAfterSessionRelease)$'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--output',default='validation-v1');a=p.parse_args()
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
commands=[]
for label,race in [('normal',False),('race',True)]:
 cmd=[GO,'test','-json','-mod=readonly','-overlay='+str(HERE/'test-overlay.json')]
 if race:cmd.append('-race')
 commands.append({'label':label,'argv':cmd+['./core/schema','-run',PATTERN,'-count=1']})
if not a.run:print(json.dumps({'execute':False,'commands':commands,'cloud_calls':0,'engine_calls':0}));raise SystemExit
assert a.output.startswith('validation-v')and '/'not in a.output
out=HERE/a.output;assert not out.exists()
expected=json.loads((HERE/'hashes.json').read_text())
for name,want in expected.items():assert sha(HERE/name)==want,name
provenance=json.loads((HERE.parent/'source-provenance.json').read_text())
for path,want in provenance['source'].items():assert sha(path)==want,path
out.mkdir();(out/'validate.py.txt').write_bytes(Path(__file__).read_bytes())
env=os.environ.copy();env.update(GOMAXPROCS='4',GOPROXY='off',GOTOOLCHAIN='local')
results={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'script_sha256':sha(__file__),'input_hashes':expected,'runs':[]}
for command in commands:
 log=out/(command['label']+'.jsonl');start=time.monotonic()
 with log.open('w')as f:result=subprocess.run(command['argv'],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
 events=[]
 for line in log.read_text().splitlines():
  try:events.append(json.loads(line))
  except json.JSONDecodeError:pass
 row=dict(command,exit_code=result.returncode,seconds=time.monotonic()-start,log_sha256=sha(log),
  failures=[e['Test']for e in events if e.get('Action')=='fail'and 'Test'in e],
  passes=[e['Test']for e in events if e.get('Action')=='pass'and 'Test'in e])
 results['runs'].append(row);(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(json.dumps({k:row[k]for k in ('label','exit_code','seconds','failures')}),flush=True)
 assert result.returncode==0
results['all_passed']=True;(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
