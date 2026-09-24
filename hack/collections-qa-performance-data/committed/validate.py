from pathlib import Path
import subprocess,os,json,time
base=Path('/tmp/collections-perf/committed');out=base/'validation';out.mkdir(exist_ok=True)
env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
env.update({'DAGGER_ENGINE':'container://dagger-engine.collections-committed-candidate-0','_EXPERIMENTAL_DAGGER_CLI_BIN':str(base/'dagger'),'DAGGER_SRC_ROOT':'/home/dagger/dag','DAGGER_BIN_ROOT':str(base)})
rows=[]
def run(name,args,cwd):
 t=time.monotonic()
 with (out/(name+'.log')).open('w') as log:
  p=subprocess.run(args,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
 row={'name':name,'exit_code':p.returncode,'seconds':time.monotonic()-t,'command':args};rows.append(row);(out/'summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
 return p.returncode
run('collections-integration',['go','test','-v','./core/integration','-count=1','-parallel=1','-run','^TestCollections$/(TestCLI|TestCommandLists|TestCommandListSchemaPaths|TestListFormats|TestLargeCollectionListOutput|TestCheckSelection|TestDimensionItems|TestBatchReplacement)$'],'/home/dagger/dag')
run('dang-boundaries',['go','test','-v','./core/integration','-count=1','-parallel=1','-run','^(TestDang|TestDangForcing)$/(TestDirectives|TestSDKClientAttachables|TestWorkspaceArg|TestVersionedSyntax|TestSelfCallReturningOwnType|TestLazyChainForcing)$'],'/home/dagger/dag')
for name,cli,engine,ws in [
 ('module-original','/tmp/collections-perf/untouched-pr/dagger','dagger-engine.collections-committed-original-0','/tmp/collections-perf/untouched-pr/qa-original'),
 ('module-candidate',str(base/'dagger'),'dagger-engine.collections-committed-candidate-0','/tmp/collections-perf/untouched-pr/qa-optimized')]:
 run(name,[cli,'--engine','container://'+engine,'--workspace',ws,'check','-m',ws+'/.dagger/modules/go-dev','--generated=false','discovery-check','discovery-from-subdir-check','collection-check','tests-collection-check','module-introspection-check','skips-non-modules-check'],ws)
# The same selected-test batching probe used for the historical prototype.
s=Path('/tmp/collections-perf/greetings/batch-qa.py').read_text()
s=s.replace("base=Path('/tmp/collections-perf/greetings/batch-qa')","base=Path('/tmp/collections-perf/committed/greetings/batch-qa')")
s=s.replace('/tmp/collections-perf/dagger-pinned-discovery',str(base/'dagger'))
s=s.replace('dagger-engine.collections-untouched','dagger-engine.collections-committed-original-0').replace('dagger-engine.collections-profile-stack','dagger-engine.collections-committed-candidate-0')
s=s.replace('/tmp/greetings-api-collections-perf',str(base/'greetings/warm-workspace-original')).replace('/tmp/greetings-api-optimized-perf',str(base/'greetings/warm-workspace-candidate'))
s=s.replace('6080','6090').replace('6066','6091').replace('full-stack','candidate')
(base/'batch-qa.py').write_text(s)
run('selected-tests',[os.sys.executable,str(base/'batch-qa.py')],str(base))
if any(row['exit_code'] for row in rows):raise SystemExit(1)
