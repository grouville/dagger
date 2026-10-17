from pathlib import Path
import gzip,hashlib,json,os,signal,socket,subprocess,threading,time,urllib.request
protocol=Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
exec(protocol.read_text().split('fixtures = [f for f')[0])
cli=base/'filesync-literal-pathwalk/dagger-after'
workspace=Path('/tmp/dagger-go-real-repository-main');module=Path('/tmp/dagger-go-module-test-name-index')
source=workspace/'dagql/types.go';original=source.read_bytes()
configs={n:(workspace/n).read_bytes() if (workspace/n).exists() else None for n in ['dagger.toml','dagger.lock']}
routes=['batch-metadata','attribute-array-decode','reusable-declarations','span-lookup-fanout','span-resource-batches','lazy-type-maps','telemetry-flush-coalescing','callback-caller-reuse']
flags={r:get(r)['enabled'] for r in routes}
seed_path='/tmp/filesync-snapshot-seeds-mode';seeds=subprocess.check_output(['docker','exec',record['Id'],'cat',seed_path])
cli_address='127.0.0.1:16697';cli_debug='http://'+cli_address+'/debug/'
probe=socket.socket();probe.bind(('127.0.0.1',16697));probe.close()
env.pop('CPUPROFILE',None);env['PPROF']=cli_address;env['_EXPERIMENTAL_DAGGER_VERSION']='v1.0.0-beta.15'
def raw(url,timeout=20):
 with urllib.request.urlopen(url,timeout=timeout) as response:return response.read()
stop=threading.Event();samples=[];windows=[];errors=[]
def sample():
 while not stop.wait(1):
  row=dict(seconds=time.monotonic()-tick,engine_heap=heap(),engine_cpu=cpu(),pressure=pressure())
  try:
   mem=json.loads(raw(cli_debug+'vars',5))['memstats']
   row['cli_heap']={k:mem[k] for k in ['HeapAlloc','TotalAlloc','Mallocs','NumGC']}
  except Exception as error:row['cli_debug_error']=str(error)
  samples.append(row)
def cli_cpu():
 while not stop.is_set():
  try:identity=raw(cli_debug+'pprof/cmdline',2);break
  except OSError:
   if stop.wait(.05):return
 (root/'cli-cmdline.txt').write_bytes(identity)
 index=0
 while not stop.is_set():
  begin=time.monotonic()
  try:
   data=raw(cli_debug+'pprof/profile?seconds=3',12)
   name=f'cli-cpu-{index:03d}.pprof';(root/name).write_bytes(data)
   windows.append(dict(path=name,start_seconds=begin-tick,end_seconds=time.monotonic()-tick,bytes=len(data)))
  except Exception as error:
   errors.append(dict(scope='cli_cpu',start_seconds=begin-tick,error=str(error),command_finished=stop.is_set()))
   if stop.wait(1):break
   raise
  index+=1

assert not get('wcprof/enabled')['global_enabled']
assert not get('snapshot-collection')['deferred']
assert get('collection-expansion-limit')['limit']==0
idle('profile-cli')
metadata=dict(scope='Diagnostic full Go listing with CLI CPU windows and wcprof. No Go runtime trace, engine CPU sampler, forced GC or telemetry suppression. Counters and profiles are diagnostic only; the time is excluded from latency cohorts.',cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],workspace_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=workspace,text=True).strip(),module_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=module,text=True).strip(),warm_engine=True,fresh_cli=True,fresh_source_edit=True,telemetry=True,ordinary_gc=True,resource_batch_reuse=True,cli_cpu_window_seconds=3,flags_before=flags)
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(root/'driver.py').write_bytes(Path(__file__).read_bytes())
threads=[];cancelled=False
try:
 for route in ['batch-metadata','attribute-array-decode','reusable-declarations','span-lookup-fanout','span-resource-batches']:mode(route,True)
 for route in ['lazy-type-maps','telemetry-flush-coalescing','callback-caller-reuse']:mode(route,False)
 get('span-resource-batches?record=true',b'')
 subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=b'on\n',check=True)
 source.write_bytes(original+f'\n// Profile complete Go listing CLI {time.time_ns()}\n'.encode())
 (workspace/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
 get('wcprof/enabled',b'on');raw(debug+'wcprof/dump')
 tick=time.monotonic();wall=time.time();before=heap();before_cpu=cpu();before_pressure=pressure()
 command=[str(cli),'check','--module','go','--check','test','--list','--all']
 timed=['/usr/bin/time','-f','{"user_seconds":%U,"system_seconds":%S,"max_rss_kib":%M}','-o',str(root/'cli-resources.json'),'--',*command]
 with (root/'command.stdout').open('w') as out,(root/'command.stderr').open('w') as err:
  process=subprocess.Popen(timed,cwd=workspace,env=env,stdout=out,stderr=err,start_new_session=True)
  threads=[threading.Thread(target=sample),threading.Thread(target=cli_cpu)]
  for thread in threads:thread.start()
  try:code=process.wait(timeout=300)
  except subprocess.TimeoutExpired:cancelled=True;os.killpg(process.pid,signal.SIGINT);code=process.wait()
 elapsed=time.monotonic()-tick;after=heap();after_cpu=cpu();after_pressure=pressure()
 resources=get('span-resource-batches')
finally:
 stop.set()
 for thread in threads:thread.join()
 get('wcprof/enabled',b'off')
 source.write_bytes(original)
 for n,data in configs.items():
  if data is None:(workspace/n).unlink(missing_ok=True)
  else:(workspace/n).write_bytes(data)
 get('span-resource-batches?record=false',b'')
 for route,enabled in flags.items():mode(route,enabled)
 subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=seeds,check=True)
(root/'samples.json').write_text(json.dumps(samples,indent=2)+'\n');(root/'cli-cpu-windows.json').write_text(json.dumps(windows,indent=2)+'\n')
chunks=[];events=[];deadline=time.monotonic()+120
while True:
 data=raw(debug+'wcprof/dump',45);(root/f'wcprof-{len(chunks)}.ndjson.gz').write_bytes(gzip.compress(data,mtime=0))
 lines=data.splitlines();header=json.loads(lines[0]);chunks.append(header);events.extend(lines[1:])
 if not header.get('open_ops'):break
 assert time.monotonic()<deadline,'wcprof operations still open';time.sleep(1)
header=dict(chunks[-1]);header['event_count']=len(events)
(root/'wcprof-complete.ndjson').write_bytes((json.dumps(header)+'\n').encode()+b'\n'.join(events)+b'\n')
listed=[s for s in (root/'command.stdout').read_text().splitlines() if s.startswith('go ')]
expected=[s for s in (base/'go-wide-trace-index/profile-fast/command.stdout').read_text().splitlines() if s.startswith('go ')]
result=dict(seconds=elapsed,exit_code=code,cancelled=cancelled,rows=len(listed),same_rows=listed==expected,engine_cpu=after_cpu-before_cpu,engine_heap_delta={k:after[k]-before[k] for k in before},cli_resources=json.loads((root/'cli-resources.json').read_text().splitlines()[-1]),resource_counts=resources,cli_cpu_windows=len(windows),errors=errors,recorder=dict(events=len(events),dropped=header['dropped_events'],open=len(header.get('open_ops',[]))),restored_source=hashlib.sha256(source.read_bytes()).hexdigest()==hashlib.sha256(original).hexdigest())
(root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
assert code==0 and not cancelled and len(listed)==4398 and listed==expected and not header.get('open_ops')
