from pathlib import Path
from types import SimpleNamespace
import json,os,signal,subprocess,threading,time,urllib.request
out=Path('/tmp/go-collection-upstream-review-oct19')
cli=Path('/tmp/go-collection-clean-branches/main-dagger')
helper=['python3','/tmp/rust-cache-sipsma-review/local_cli_collector.py']
a=SimpleNamespace(task='go')
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
