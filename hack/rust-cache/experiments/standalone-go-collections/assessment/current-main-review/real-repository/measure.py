from pathlib import Path
import argparse,json,os,signal,subprocess,threading,time,urllib.request,gzip,socket
p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--cli',default='/tmp/go-collection-clean-branches/main-dagger');p.add_argument('--profile',action='store_true');p.add_argument('--add-test',action='store_true');p.add_argument('--timeout',type=int,default=240);a=p.parse_args()
u=Path('/tmp/go-collection-clean-branches/real-repository');out=u/a.label;out.mkdir(exist_ok=False)
source=Path('/tmp/dagger-go-collection-current-main');debug='http://127.0.0.1:16130/debug/'
def raw(route,data=None,timeout=30):
 with urllib.request.urlopen(debug+route,data=data,timeout=timeout) as r:return r.read()
assert not json.loads(raw('wcprof/enabled'))['global_enabled']
original=(u/'types.go.original').read_bytes();test_original=(u/'cache_test.go.original').read_bytes()
(source/'dagql/types.go').write_bytes(original+f'\n// Collection listing verification {time.time_ns()}\n'.encode())
marker='TestCollectionReviewAdded'
(source/'dagql/cache_test.go').write_bytes(test_original+(f'\nfunc {marker}(t *testing.T) {{}}\n'.encode() if a.add_test else b''))
env=dict(os.environ,GOMAXPROCS='8',RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16310',RUST_CACHE_BENCH_CLI=a.cli,RUST_CACHE_BENCH_COLLECTOR='http://'+Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip()+':43184',_EXPERIMENTAL_DAGGER_CLI_BIN=a.cli,_EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.19')
for key in ['PPROF','CPUPROFILE']:env.pop(key,None)
stop=threading.Event();cpu_windows=[];profile_errors=[];threads=[]
def profile_engine():
 index=0
 while not stop.is_set():
  start=time.monotonic()
  try:
   data=raw('pprof/profile?seconds=5',timeout=15);name=f'engine-cpu-{index:03d}.pprof';(out/name).write_bytes(data)
   cpu_windows.append(dict(path=name,start=start-tick,end=time.monotonic()-tick));index+=1
  except Exception as e:profile_errors.append(str(e));break
if a.profile:
 raw('wcprof/enabled',b'on');(out/'wcprof-before.ndjson.gz').write_bytes(gzip.compress(raw('wcprof/dump'),mtime=0))
 (out/'engine-allocs-before.pprof').write_bytes(raw('pprof/allocs'))
 sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();env['PPROF']=f'127.0.0.1:{port}'
cli_profiles=[]
def profile_cli():
 route=f'http://127.0.0.1:{port}/debug/pprof/'
 while not stop.wait(.05):
  try:
   urllib.request.urlopen(route,timeout=1).close();break
  except OSError:pass
 index=0
 while not stop.is_set():
  start=time.monotonic()
  try:
   with urllib.request.urlopen(route+'profile?seconds=5',timeout=15) as r:data=r.read()
   name=f'cli-cpu-{index:03d}.pprof';(out/name).write_bytes(data);cli_profiles.append(dict(path=name,start=start-tick,end=time.monotonic()-tick));index+=1
  except OSError as e:
   if not stop.is_set():profile_errors.append(str(e))
   break
command=['python3','/tmp/rust-cache-sipsma-review/local_cli_collector.py','check','--module','go','--check','test','--list','--all']
rows=[];row_times=[];tick=time.monotonic();timed_out=False
try:
 with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
  process=subprocess.Popen(command,cwd=source,env=env,stdout=subprocess.PIPE,stderr=stderr,text=True,start_new_session=True)
  def read_stdout():
   for line in process.stdout:
    stdout.write(line);stdout.flush()
    if line.startswith('go '):rows.append(line.rstrip('\n'));row_times.append(time.monotonic()-tick)
  reader=threading.Thread(target=read_stdout);reader.start()
  if a.profile:
   threads=[threading.Thread(target=profile_engine),threading.Thread(target=profile_cli)]
   for thread in threads:thread.start()
  while process.poll() is None:
   elapsed=time.monotonic()-tick
   if elapsed>a.timeout:
    timed_out=True;os.killpg(process.pid,signal.SIGINT)
    try:process.wait(timeout=45)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=15)
    break
   try:process.wait(timeout=15)
   except subprocess.TimeoutExpired:print(json.dumps(dict(event='running',label=a.label,seconds=round(time.monotonic()-tick,1),rows=len(rows))),flush=True)
  elapsed=time.monotonic()-tick;reader.join(timeout=10)
 code=process.returncode
finally:
 stop.set()
 if a.profile:raw('wcprof/enabled',b'off')
 for thread in threads:thread.join(timeout=20)
 (source/'dagql/types.go').write_bytes(original);(source/'dagql/cache_test.go').write_bytes(test_original)
if a.profile:
 (out/'engine-allocs-after.pprof').write_bytes(raw('pprof/allocs'))
 data=raw('wcprof/dump',timeout=60);(out/'wcprof.ndjson.gz').write_bytes(gzip.compress(data,mtime=0))
 (out/'profile-windows.json').write_text(json.dumps(dict(engine=cpu_windows,cli=cli_profiles,errors=profile_errors),indent=2)+'\n')
result=dict(label=a.label,seconds=elapsed,exit_code=code,timed_out=timed_out,rows=len(rows),first_row_seconds=row_times[0] if row_times else None,last_row_seconds=row_times[-1] if row_times else None,cli=a.cli,profile=a.profile,add_test=a.add_test,marker_count=sum(marker in r for r in rows),fresh_cli=True,source_edit=True,telemetry=True,cleanup_included=True)
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
assert code==0 and not timed_out
assert rows and result['marker_count']==int(a.add_test)
