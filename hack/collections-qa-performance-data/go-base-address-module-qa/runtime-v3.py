"""Prepared THREE local GoDev correctness checks. No timing or Cloud claim."""
from pathlib import Path
import argparse,hashlib,json,re,sys
H=Path(__file__).resolve().parent;L=Path('/tmp/collections-perf/go-base-address-retained-v1');W=H/'workspace-v3'
A=argparse.ArgumentParser();A.add_argument('--run',action='store_true');a=A.parse_args()
if not a.run:print(json.dumps({'local_cli_cap':3,'cloud_calls':0,'prepared_only':True,'workspace':str(W)}));raise SystemExit
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
frozen=json.loads((H/'source-manifest-v3.json').read_text())
for p,want in frozen['source_hashes'].items():assert sha(p)==want,p
fixture=json.loads((H/'fixture-manifest-v3.json').read_text());assert fixture['source_manifest_sha256']==sha(H/'source-manifest-v3.json')
sys.path.insert(0,str(L));from lifecycle import EngineLifecycle,ANSI
out=L/'godev-results-v3';assert not out.exists()
def guard():
 actual={str(p.relative_to(W)):sha(p)for p in W.rglob('*')if p.is_file()and'.git'not in p.relative_to(W).parts}
 assert {p:h for p,h in actual.items()if p!='dagger.lock'}=={p:h for p,h in fixture['files'].items()if p!='dagger.lock'}
checks=['base-address-discovery-check','base-address-execution-check','base-check'];summary={'local_cli_cap':3,'cloud_calls':0,'scope':'module constructor policy, deferred discovery and custom-base test/generate correctness only','status':'incomplete'}
try:
 guard()
 with EngineLifecycle(out,3)as engine:
  for check in checks:
   def validate(row,stdout,stderr,check=check):
    text=ANSI.sub(b'',stdout+b'\n'+stderr)
    return row['exit_code']==0 and re.search(rb'\b1 passed\b',text)is not None and re.search(rb'\b[1-9][0-9]* failed\b',text)is None and b'SKIP'not in text and check.encode()in text
   engine.run(['check','go-dev/'+check],W,validate,check,timeout=600);guard()
  assert len(engine.rows)==3 and all(row['correct']for row in engine.rows)
  summary['status']='passed';summary['validated_commands']=3
finally:
 guard();summary['fixture_authored_source_unchanged']=True;summary['candidate_go_sha256']=sha(W/'go.dang');summary['source_manifest_sha256']=sha(H/'source-manifest-v3.json')
 (H/'summary-v3.json').write_text(json.dumps(summary,indent=2)+'\n')
