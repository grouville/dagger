from pathlib import Path
import hashlib,json,os,signal,subprocess,time
u=Path('/tmp/go-collection-clean-branches');out=u/'remaining-verification';out.mkdir(exist_ok=True)
print('QUEUED: waiting for the full-repository profile before starting tests',flush=True)
while not (u/'real-repository/profile-main/result.json').exists():time.sleep(2)
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off');rows=[]
def record(row):
 rows.append(row);(out/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
def run(label,command,cwd,runenv=env,negative=False,needle=None):
 print(json.dumps(dict(event='start',label=label)),flush=True);start=time.monotonic()
 with (out/(label+'.log')).open('w') as log:
  process=subprocess.Popen(command,cwd=cwd,env=runenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=process.wait(timeout=240)
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGINT);code=process.wait(timeout=45)
 text=(out/(label+'.log')).read_text()
 okay=(code!=0 and needle in text and 'build failed' not in text) if negative else code==0
 row=dict(label=label,command=command,cwd=str(cwd),seconds=time.monotonic()-start,exit_code=code,expected_failure=negative,verified=okay,log=label+'.log');record(row)
 if not okay:print(text[-3500:],flush=True)
 return okay
# New batching experiment: the existing selection checks plus the added order/normalization check.
module=Path('/tmp/go-collection-batch-main-selection')
runenv=dict(env,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16310',RUST_CACHE_BENCH_CLI=str(u/'main-dagger'),RUST_CACHE_BENCH_COLLECTOR='http://'+Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip()+':43184',_EXPERIMENTAL_DAGGER_CLI_BIN=str(u/'main-dagger'),_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.19')
for check in ['gomod-checks:batched-selection-check','gomod-checks:selection-check','go-dev:selection-check','go-dev:binary-check']:
 if not run('batch-'+check.replace(':','-'),['python3','/tmp/rust-cache-sipsma-review/local_cli_collector.py','check',check],module,runenv):break
# The prepared Dagger fixes: reproduce on today's main, then apply just the fix.
base=Path('/tmp/dagger-go-collection-clean-baseline')
for ident,production,test,pattern in [('class-history','dagql/objects.go','dagql/class_fork_history_test.go','TestClassForkHistoryIsolation'),('list-types','core/sdk/dang/v2/helpers.go','core/sdk/dang/v2/list_conversion_test.go','TestConvertListPreservesElementType')]:
 target=out/ident
 subprocess.run(['git','-c','gc.auto=0','-C',str(base),'worktree','add','--detach',str(target),'c5456d9cbf47e432b89aba43e35211425e8e1f03'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 branch='pr/go-collections-'+ident
 (target/test).write_bytes(subprocess.check_output(['git','-C',str(base),'show',branch+':'+test]))
 package='./'+str(Path(production).parent)
 command=[go,'test','-p=2','-race','-count=1','-timeout=180s','-run','^'+pattern+'$',package]
 assert run(ident+'-main-repro',command,target,negative=True,needle='--- FAIL: '+pattern)
 patch=subprocess.check_output(['git','-C',str(base),'diff','80699ac67a1c72dc38d30c4186105cd9dd3afde6',branch,'--',production])
 subprocess.run(['git','-C',str(target),'apply','--whitespace=error','-'],input=patch,check=True)
 assert run(ident+'-fixed',command,target)
# Each Dang proposal is tested independently on the newer main, never stacked.
base=Path('/tmp/go-collection-clean-dang');current='bf649b8dd99f321984bc9cd9d1a3494acf2c0c39'
old='da1bed304cb80f8a2f0714f1747e7f64e03297a3'
for row in json.loads((u/'dang-branches.json').read_text()):
 ident=row['id'];target=out/('dang-'+ident)
 subprocess.run(['git','-c','gc.auto=0','-C',str(base),'worktree','add','--detach',str(target),current],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if ident=='nested-selection':
  test='pkg/dang/nested_selection_elements_test.go';(target/test).write_bytes(subprocess.check_output(['git','-C',str(base),'show',row['head']+':'+test]))
  command=[go,'test','-p=2','-race','-count=1','-timeout=180s','-run','^TestNestedSelectionPreservesElementNullability$','./pkg/dang']
  assert run('dang-nested-selection-main-repro',command,target,negative=True,needle='--- FAIL: TestNestedSelectionPreservesElementNullability')
  files=['pkg/dang/ast_expressions.go']
 else:files=row['files']
 patch=subprocess.check_output(['git','-C',str(base),'diff',old,row['head'],'--',*files])
 result=subprocess.run(['git','-C',str(target),'apply','--whitespace=error','-'],input=patch,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 if result.returncode:
  record(dict(label='dang-'+ident+'-apply',verified=False,reason='The patch no longer applies to current main; it needs a fresh review, not publication.',details=result.stderr.decode()));continue
 run('dang-'+ident+'-current-main-race',[go,'test','-p=2','-race','-count=1','-timeout=180s','./pkg/dang'],target)
(out/'complete.json').write_text(json.dumps(dict(complete=True,all_verified=all(r['verified'] for r in rows),checks=len(rows)),indent=2)+'\n')
