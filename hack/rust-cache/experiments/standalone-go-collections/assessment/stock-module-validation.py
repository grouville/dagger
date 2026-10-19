from pathlib import Path
import hashlib,json,os,signal,statistics,subprocess,time

unit=Path('/tmp/go-collection-clean-branches')
root=Path('/home/dagger/dagger_otra')
baseline=Path('/tmp/dagger-go-collection-clean-baseline')
module=Path('/tmp/go-collection-clean-go')
control=Path('/tmp/go-collection-clean-go-main')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='8',GOTOOLCHAIN='local',GOWORK='off',GOPROXY='off',GOSUMDB='off')
while not (unit/'post-validation-complete.json').exists():time.sleep(2)
builds=[]
for name,target in [('main-dagger-engine','./cmd/engine'),('main-dagger','./cmd/dagger')]:
 command=[go,'build','-p=2','-buildvcs=false','-o',str(unit/name),target]
 buildenv=dict(env,CGO_ENABLED='0') if target=='./cmd/dagger' else env
 start=time.monotonic()
 print(json.dumps(dict(event='stock-build-start',target=target)),flush=True)
 with (unit/(name+'-build.log')).open('w') as log:
  result=subprocess.run(command,cwd=baseline,env=buildenv,stdout=log,stderr=subprocess.STDOUT)
 builds.append(dict(command=command,exit_code=result.returncode,seconds=time.monotonic()-start,target=target,cgo_enabled=buildenv.get('CGO_ENABLED','toolchain default')))
 (unit/'main-builds.json').write_text(json.dumps(builds,indent=2)+'\n')
 assert result.returncode==0,(unit/(name+'-build.log')).read_text()[-3000:]
subprocess.run(['python3',str(unit/'start-main-engine.py')],check=True)
subprocess.run(['git','-c','gc.auto=0','-C',str(module),'worktree','add','--detach',str(control),'334136faaa1cd36ac26dfdc648eda907ce99c063'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
runenv=dict(env,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16310',RUST_CACHE_BENCH_CLI=str(unit/'main-dagger'),RUST_CACHE_BENCH_COLLECTOR='http://'+Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip()+':43184',_EXPERIMENTAL_DAGGER_CLI_BIN=str(unit/'main-dagger'),_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.19')
helper=['python3','/tmp/rust-cache-sipsma-review/local_cli_collector.py']
rows=json.loads((unit/'go-branches.json').read_text());checks=[];samples=[]
listing=['check','--module','go','--check','test','--list','--all']
def run(label,cwd,args):
 start=time.monotonic()
 with (unit/(label+'.stdout')).open('w') as stdout,(unit/(label+'.stderr')).open('w') as stderr:
  process=subprocess.Popen([*helper,*args],cwd=cwd,env=runenv,stdout=stdout,stderr=stderr,start_new_session=True)
  try:code=process.wait(timeout=240)
  except subprocess.TimeoutExpired:
   os.killpg(process.pid,signal.SIGINT);code=process.wait(timeout=60)
   raise RuntimeError('timed out '+label)
 seconds=time.monotonic()-start
 assert code==0,(label,(unit/(label+'.stderr')).read_text()[-3000:])
 return seconds,(unit/(label+'.stdout')).read_text()

for row in rows:
 subprocess.run(['git','-C',str(module),'switch',row['branch']],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 selected=['generation-globs-check','selection-check','generate-check']
 if row['id']=='generation-matches':selected.append('generation-discovery-check')
 for check in selected:
  label='stock-'+row['id']+'-'+check
  print(json.dumps(dict(event='stock-go-check-start',id=row['id'],check=check)),flush=True)
  seconds,_=run(label,module,['check','go-dev:'+check])
  checks.append(dict(id=row['id'],check=check,seconds=seconds,exit_code=0,log=label+'.stderr'))
  (unit/'stock-go-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
 workspace=unit/('listing-fixture-'+row['id']);workspace.mkdir()
 subprocess.run(['git','init','--quiet',str(workspace)],check=True)
 (workspace/'go.mod').write_text('module example.com/collectionfixture\n\ngo 1.26.6\n')
 expected=[]
 for n in range(16):
  path=workspace/f'mod_{n:03d}';path.mkdir()
  (path/'go.mod').write_text(f'module example.com/mod{n}\n\ngo 1.26.6\n')
  (path/'value.go').write_text('package fixture\n\nfunc Value() int { return 42 }\n')
  (path/'value_test.go').write_text('package fixture\n\nimport "testing"\n\nfunc TestValue(t *testing.T) { if Value() != 42 { t.Fatal("value") } }\n')
  expected.append((f'mod_{n:03d}','TestValue'))
 source=workspace/'mod_000/value.go';test=workspace/'mod_000/value_test.go'
 original_source=source.read_bytes();original_test=test.read_bytes()
 arms={'before':control,'candidate':module}
 for scenario in ['source','test']:
  for pair in range(-2,4):
   observed=None
   for arm in (['before','candidate'] if pair%2==0 else ['candidate','before']):
    source.write_bytes(original_source+(f'\n// standalone source edit {time.time_ns()}\n'.encode() if scenario=='source' else b''))
    test.write_bytes(original_test+(f'\n// standalone test edit {time.time_ns()}\n'.encode() if scenario=='test' else b''))
    adding=pair==-2
    if adding:test.write_bytes(test.read_bytes()+b'\nfunc TestAddedStandalone(t *testing.T) {}\n')
    (workspace/'dagger.toml').write_text('[modules.go]\nsource = "'+str(arms[arm])+'"\n[modules.go.settings]\nversion = "1.26.6"\ntest = ["**"]\n')
    label=f'stock-list-{row["id"]}-{scenario}-{pair}-{arm}'
    print(json.dumps(dict(event='stock-list-start',id=row['id'],scenario=scenario,pair=pair,arm=arm)),flush=True)
    seconds,text=run(label,workspace,listing)
    lines=[l for l in text.splitlines() if l.startswith('go ')]
    names=[tuple(l.split()[1:3]) for l in lines]
    wanted=sorted(expected+([('mod_000','TestAddedStandalone')] if adding else []))
    assert names==wanted,(label,names,wanted)
    if observed is None:observed=lines
    assert lines==observed,(label,'different output')
    sample=dict(id=row['id'],scenario=scenario,pair=pair,arm=arm,warmup=pair<0,seconds=seconds,exit_code=0,rows=len(names),correct_names=True,same_full_rows=True,label=label,engine_main='80699ac67a1c72dc38d30c4186105cd9dd3afde6',module_main='334136faaa1cd36ac26dfdc648eda907ce99c063',candidate_head=row['head'],module_count=16,fresh_cli=True,telemetry=True,cleanup_included=True)
    samples.append(sample);(unit/'stock-listing-samples.json').write_text(json.dumps(samples,indent=2)+'\n')
    print(json.dumps(dict(event='stock-list-finish',**sample)),flush=True)
 source.write_bytes(original_source);test.write_bytes(original_test)
 summary=[]
 for scenario in ['source','test']:
  group=[s for s in samples if s['id']==row['id'] and s['scenario']==scenario and not s['warmup']]
  before=sorted([s for s in group if s['arm']=='before'],key=lambda s:s['pair']);after=sorted([s for s in group if s['arm']=='candidate'],key=lambda s:s['pair'])
  summary.append(dict(id=row['id'],scenario=scenario,before=statistics.median(s['seconds'] for s in before),candidate=statistics.median(s['seconds'] for s in after),faster_pairs=sum(b['seconds']<a['seconds'] for a,b in zip(before,after)),median_paired_saving=statistics.median(a['seconds']-b['seconds'] for a,b in zip(before,after))))
 (unit/(row['id']+'-stock-listing-summary.json')).write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(dict(event='stock-listing-complete',id=row['id'],summary=summary)),flush=True)
(unit/'stock-module-validation-complete.json').write_text(json.dumps(dict(complete=True,checks=len(checks),commands=len(samples)),indent=2)+'\n')
