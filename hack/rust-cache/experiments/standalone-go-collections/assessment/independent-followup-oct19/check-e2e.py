from pathlib import Path
import argparse,json,os,re,signal,socket,statistics,subprocess,time,threading,urllib.request
p=argparse.ArgumentParser();p.add_argument('--task',choices=['go','dang'],required=True);p.add_argument('--pairs',type=int,default=4);a=p.parse_args()
out=Path('/tmp/go-collection-upstream-review-oct19');cli=Path('/tmp/go-collection-clean-branches/main-dagger');module=Path('/tmp/go-collection-clean-go-main')
engine_image='sha256:af521f4adb6de430d63a79b4c14dbd162e21c7e6d0cf207f7dcfbf716857c370'
helper=['python3','/tmp/rust-cache-sipsma-review/local_cli_collector.py'];command=['check','--module','go','--check','test','--list','--all']
def request(debug,route,data=None):
 with urllib.request.urlopen(debug+'/debug/'+route,data=data,timeout=10) as r:return json.loads(r.read())
def engine_info(name,runner,debug):
 record=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
 path=Path('/sys/fs/cgroup')/Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':',2)[2].strip().lstrip('/')
 assert not request(debug,'wcprof/enabled')['global_enabled']
 return dict(name=name,runner=runner,debug=debug,cgroup=str(path))
def cpu(engine):return int(next(line.split()[1] for line in (Path(engine['cgroup'])/'cpu.stat').read_text().splitlines() if line.startswith('usage_usec ')))/1e6
def heap(engine):return {k:v for k,v in request(engine['debug'],'vars')['memstats'].items() if k in ['TotalAlloc','Mallocs','HeapAlloc','NumGC']}
def pressure():return int(Path('/proc/pressure/cpu').read_text().splitlines()[0].split('total=')[1])
def start_engines():
 saved=out/'runtime-engines.json'
 records=json.loads(saved.read_text()) if saved.exists() else {}
 for arm in ['main','typed','callback','span']:
  if arm in records or not (out/('runtime-'+arm+'-engine')).exists():continue
  name='dagger-collection-dang-'+arm+'-review-oct19'
  assert not subprocess.check_output(['docker','ps','-aq','--filter','name=^/'+name+'$'],text=True).strip()
  assert name not in subprocess.check_output(['docker','volume','ls','--format','{{.Name}}'],text=True).splitlines()
  cmd=['docker','create','--name',name,'--label','codex.task=go-collection-independent-dang-review','--privileged','--env','GOMAXPROCS=8','-p','127.0.0.1::1234','-p','127.0.0.1::6060','--mount','type=volume,source='+name+',target=/var/lib/dagger',engine_image,'--addr','tcp://0.0.0.0:1234','--debugaddr','0.0.0.0:6060']
  subprocess.run(cmd,check=True,stdout=subprocess.PIPE);subprocess.run(['docker','cp',str(out/('runtime-'+arm+'-engine')),name+':/usr/local/bin/dagger-engine'],check=True)
  subprocess.run(['docker','start',name],check=True,stdout=subprocess.PIPE)
  inspect=json.loads(subprocess.check_output(['docker','inspect',name],text=True))[0]
  ports=inspect['NetworkSettings']['Ports'];runner='tcp://127.0.0.1:'+ports['1234/tcp'][0]['HostPort'];debug='http://127.0.0.1:'+ports['6060/tcp'][0]['HostPort']
  deadline=time.monotonic()+30
  while True:
   try:records[arm]=engine_info(name,runner,debug);break
   except OSError:
    assert time.monotonic()<deadline;time.sleep(.2)
  saved.write_text(json.dumps(records,indent=2)+'\n')
 return records
if a.task=='dang':
 engines=start_engines();tasks=[('typed-methods',dict(before=(module,engines['main']),candidate=(module,engines['typed']))),('callback-caller',dict(before=(module,engines['main']),candidate=(module,engines['callback'])))]
else:
 subprocess.run(['python3',str(out/'build-span-engine.py')],check=True)
 runtime=start_engines()
 engine=engine_info('dagger-collection-standalone-main-oct19','tcp://127.0.0.1:16310','http://127.0.0.1:16130')
 tasks=[('span-index',dict(before=(module,runtime['main']),candidate=(module,runtime['span'])))]+[(name,dict(before=(module,engine),candidate=(out/('go-'+name),engine))) for name in ['batch-selection','parallel-discovery','generation-matches','ownership']]
rows=[];checks=[]
file=out/(a.task+'-e2e-samples.json')
def run(label,cwd,args,engine):
 env=dict(os.environ,GOMAXPROCS='8',RUST_CACHE_BENCH_RUNNER=engine['runner'],RUST_CACHE_BENCH_CLI=str(cli),RUST_CACHE_BENCH_COLLECTOR='http://'+Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip()+':43184',_EXPERIMENTAL_DAGGER_CLI_BIN=str(cli),_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.19')
 logdir=out/(a.task+'-e2e-logs');logdir.mkdir(exist_ok=True)
 if a.task=='go':
  deadline=time.monotonic()+90;quiet=0
  while quiet<2:
   c0=cpu(engine);p0=pressure();start=time.monotonic();time.sleep(1);dt=time.monotonic()-start
   usage=(cpu(engine)-c0)/dt;stall=(pressure()-p0)/(dt*1e6)
   admitted=usage<.15 and stall<.10
   quiet=quiet+1 if admitted else 0
   with (out/'go-admission.jsonl').open('a') as log:log.write(json.dumps(dict(label=label,engine_cpu_per_second=usage,host_cpu_stall=stall,admitted=admitted))+'\n')
   assert time.monotonic()<deadline,('engine/host did not become quiet',label)
 h=heap(engine);c=cpu(engine);pr=pressure();memory_file=Path(engine['cgroup'])/'memory.current';memory_before=int(memory_file.read_text());memory_samples=[memory_before];stop=threading.Event()
 def sample_memory():
  while not stop.wait(.25):memory_samples.append(int(memory_file.read_text()))
 sampler=threading.Thread(target=sample_memory);sampler.start();tick=time.monotonic()
 with (logdir/(label+'.stdout')).open('w') as stdout,(logdir/(label+'.stderr')).open('w') as stderr:
  process=subprocess.Popen([*helper,*args],cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
  timed_out=False
  try:code=process.wait(timeout=240)
  except subprocess.TimeoutExpired:
   timed_out=True;os.killpg(process.pid,signal.SIGINT)
   try:code=process.wait(timeout=45)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGTERM);code=process.wait(timeout=15)
 elapsed=time.monotonic()-tick;stop.set();sampler.join();after=heap(engine)
 metrics=dict(memory_before=memory_before,peak_memory_current=max(memory_samples),memory_after=int(memory_file.read_text()),seconds=elapsed,exit_code=code,timed_out=timed_out,engine_cpu=cpu(engine)-c,allocated_bytes=after['TotalAlloc']-h['TotalAlloc'],allocations=after['Mallocs']-h['Mallocs'],gc_cycles=after['NumGC']-h['NumGC'],cpu_pressure_fraction=(pressure()-pr)/(elapsed*1e6),cleanup_successful=code==0 and not timed_out)
 return metrics,(logdir/(label+'.stdout')).read_text(),str(logdir/(label+'.stderr'))
for proposal,arms in tasks:
 if a.task=='go' and proposal not in ['generation-matches','span-index','batch-selection']:
  selected=['go-dev:discovery-check','go-dev:collection-check','go-dev:tests-collection-check','go-dev:discovery-from-subdir-check','gomod-checks:skips-non-modules-check']
  if proposal=='ownership':selected+=['go-dev:package-layout-rebind-check','go-dev:binary-check','go-dev:generate-check']
  for check in selected:
   print(json.dumps(dict(event='check',proposal=proposal,check=check)),flush=True)
   metrics,_,log=run(proposal+'-'+check.replace(':','-'),arms['candidate'][0],['check',check],arms['candidate'][1]);checks.append(dict(proposal=proposal,check=check,log=log,**metrics));(out/'go-new-port-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
   assert metrics['exit_code']==0,(proposal,check,log)
 for count,pairs in [(1,2),(16,a.pairs)]:
  workspace=out/(a.task+'-listing-fixture-'+('mains-' if proposal=='batch-selection' else '')+str(count));workspace.mkdir(exist_ok=True)
  if not (workspace/'.git').exists():subprocess.run(['git','init','--quiet',str(workspace)],check=True)
  (workspace/'go.mod').write_text('module example.com/collectionfixture\n\ngo 1.26.6\n')
  expected=[]
  for n in range(count):
   path=workspace/f'mod_{n:03d}';path.mkdir(exist_ok=True)
   (path/'go.mod').write_text(f'module example.com/mod{n}\n\ngo 1.26.6\n')
   (path/'value.go').write_text('package fixture\n\nfunc Value() int { return 42 }\n')
   (path/'value_test.go').write_text('package fixture\n\nimport "testing"\n\nfunc TestValue(t *testing.T) { if Value() != 42 { t.Fatal("value") } }\n')
   expected.append((f'mod_{n:03d}','TestValue'))
   if proposal=='batch-selection' and count==16:
    for cmd in range(4):
     command_path=path/f'cmd_{cmd:03d}';command_path.mkdir(exist_ok=True)
     (command_path/'value.go').write_text('package main\n\nfunc main() {}\nfunc Value() int { return 42 }\n')
     (command_path/'value_test.go').write_text('package main\n\nimport "testing"\nfunc TestValue(t *testing.T) { if Value() != 42 { t.Fatal("value") } }\n')
     expected.append((f'mod_{n:03d}/cmd_{cmd:03d}','TestValue'))
  source=workspace/'mod_000/value.go';test=workspace/'mod_000/value_test.go';s=source.read_bytes();t=test.read_bytes()
  try:
   for pair in range(-2,pairs):
    output=None
    for arm in (['before','candidate'] if pair%2==0 else ['candidate','before']):
     source.write_bytes(s+f'\n// Source edit {time.time_ns()}\n'.encode());test.write_bytes(t+f'\n// Test edit {time.time_ns()}\n'.encode()+(b'\nfunc TestAddedReview(t *testing.T) {}\n' if pair==-2 else b''))
     path,engine=arms[arm]
     (workspace/'dagger.toml').write_text('[modules.go]\nsource = "'+str(path)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n')
     label=f'{proposal}-{count}-{pair}-{arm}';print(json.dumps(dict(event='listing-start',label=label)),flush=True)
     metrics,text,log=run(label,workspace,command,engine)
     lines=[line for line in text.splitlines() if line.startswith('go ')];names=[tuple(line.split()[1:3]) for line in lines];wanted=sorted(expected+([('mod_000','TestAddedReview')] if pair==-2 else []))
     row=dict(proposal=proposal,modules=count,pair=pair,arm=arm,warmup=pair<0,rows=len(lines),correct_names=names==wanted,matching_rows=output is None or output==lines,log=log,fresh_cli=True,source_edit=True,test_edit=True,telemetry=True,profiling=False,**metrics);rows.append(row);file.write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
     assert row['cleanup_successful'] and row['correct_names'] and row['matching_rows'],row
     output=lines
  finally:source.write_bytes(s);test.write_bytes(t)
 summary=[]
 for count in [1,16]:
  g=[r for r in rows if r['proposal']==proposal and r['modules']==count and not r['warmup']];b=sorted([r for r in g if r['arm']=='before'],key=lambda r:r['pair']);c=sorted([r for r in g if r['arm']=='candidate'],key=lambda r:r['pair'])
  item=dict(proposal=proposal,modules=count,pairs=len(b),faster_pairs=sum(y['seconds']<x['seconds'] for x,y in zip(b,c)))
  for key in ['seconds','engine_cpu','allocated_bytes','allocations','peak_memory_current']:
   item['before_'+key]=statistics.median(r[key] for r in b);item['candidate_'+key]=statistics.median(r[key] for r in c)
  summary.append(item)
 (out/(a.task+'-'+proposal+'-e2e-summary.json')).write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(dict(event='proposal-complete',summary=summary)),flush=True)
(out/(a.task+'-e2e-complete.json')).write_text(json.dumps(dict(complete=True,commands=len(rows),checks=len(checks)),indent=2)+'\n')
