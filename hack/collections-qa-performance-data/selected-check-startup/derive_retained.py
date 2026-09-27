from pathlib import Path
import json,collections,hashlib
out=Path(__file__).resolve().parent;lab=Path('/tmp/collections-perf/engine-allocation-round2/span-runtime-v1')
p=lab/'local-diagnostic-0-selected-check-common-diagnostic/run.wcprof'
rows=json.loads((lab/'results.json').read_text());row=next(r for r in rows if r['flow']=='selected-check' and r['phase']=='local-diagnostic')
with p.open()as f:h=json.loads(next(f));ops=[e for line in f if(e:=json.loads(line))['e']=='op']
O={e['id']:e for e in ops};S=h['strings'];epoch=h['epoch_unix_nano'];zero=min(e['s']for e in ops)
fixed=['Workspace.artifacts','Artifacts.__evaluationItems','Artifacts.values','Artifact.value','Artifacts.filterCheckCommand','Address.container','Query.moduleSource','ModuleSource.asModule','backend:Query.backend','backend:Backend.goTestBase','go:Go.modules','gomod:Gomod.modules','go:GoModule.tests','go:GoTests.subset','go:GoTests.batch','go:GoTests_Batch.run','Check.sync','schema.forkPrepared','session.schemaBuild','Workspace.findRoots','Workspace.file','gomod:Gomod.workspaceRootPath']
entries=[]
for c in fixed:
 es=[e for e in ops if S[e.get('c',0)]==c]
 entries.append(dict(operation=c,count=len(es),outcomes=dict(collections.Counter(e.get('o','')for e in es)),instances=[dict(kind=e['k'],outcome=e.get('o',''),start_after_cli_ms=(epoch+e['s']-row['started_unix_ns'])/1e6,start_after_profile_ms=(e['s']-zero)/1e6,duration_ms=(e['d']-e['s'])/1e6)for e in sorted(es,key=lambda x:x['s'])]))
process=[]
for e in ops:
 if S[e.get('c',0)]!='exec.processRun':continue
 argv=json.loads(S[e.get('m',0)]);label='Go SDK runtime' if argv and Path(argv[0]).name=='runtime'else'other process'
 chain=[];n=e
 while n:
  c=S[n.get('c',0)]
  if c in fixed:chain.append(dict(operation=c,outcome=n.get('o',''),duration_ms=(n['d']-n['s'])/1e6))
  n=O.get(n.get('p'))
 process.append(dict(label=label,start_after_cli_ms=(epoch+e['s']-row['started_unix_ns'])/1e6,duration_ms=(e['d']-e['s'])/1e6,ancestor_phases=chain))
result=dict(scope='One retained local-only selected-check profile, common span diagnostic stack; no timing comparison. Ordinary later lazy-core stack may differ. Explicit generated=false is equivalent only for this exact non-generator check target.',profile_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),results_sha256=hashlib.sha256((lab/'results.json').read_bytes()).hexdigest(),cli_ms=row['seconds']*1000,profile_window_ms=(max(e['d']for e in ops)-zero)/1e6,operations=len(ops),open=len(h.get('open_ops',[])),dropped=h['dropped_events'],operations_starting_before_cli=sum(epoch+e['s']<row['started_unix_ns']for e in ops),operations_ending_after_cli=sum(epoch+e['d']>row['exited_unix_ns']for e in ops),phases=entries,processes=process,limits=['Call and call-execution wrappers describe the same work; never sum both.','Schema.forkPrepared and session.schemaBuild are explicitly instrumented; dagqlServerForModule itself is not, so its exact residual remains unmeasured.','No test-runner process occurs in this warmed profile; do not label Check.sync duration actual uncached test execution.','Runtime metadata arguments, commands, paths and opaque identifiers are not exported.'])
assert result['open']==result['dropped']==result['operations_starting_before_cli']==result['operations_ending_after_cli']==0
(out/'retained-profile-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ['phases','processes','limits']}))
