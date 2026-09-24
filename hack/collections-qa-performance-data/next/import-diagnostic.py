from pathlib import Path
import subprocess,os,time,json,socket,shutil
base=Path('/tmp/collections-perf/ts-cache/import-diagnostic');base.mkdir(exist_ok=True);ws=base/'workspace'
subprocess.run(['git','clone','--quiet','--no-local','/tmp/greetings-api-collections-perf',str(ws)],check=True,capture_output=True)
subprocess.run(['git','-C',str(ws),'remote','set-url','origin','https://github.com/kpenfound/greetings-api.git'],check=True)
for name in ['dagger.toml','dagger.lock']:shutil.copyfile(Path('/tmp/collections-perf/kyle-latest/greetings-api')/name,ws/name)
entry=ws/'.dagger/modules/frontend/__dagger.entrypoint.ts';shutil.copyfile(entry,entry.with_name('__dagger.original.ts'))
entry.write_text('''function mark(stage) { console.error("IMPORT_PERF " + JSON.stringify({stage,pid:process.pid,uptimeMs:process.uptime()*1000})); }
mark("bootstrap");
await import("./sdk/core.js"); mark("core");
await import("./sdk/client.gen.js"); mark("client");
await import("./sdk/index.ts"); mark("sdk-index");
await import("@dagger.io/dagger/telemetry"); mark("telemetry");
await import("./src/index.ts"); mark("application");
await import("./__dagger.original.ts"); mark("dispatch");
''')
env=os.environ.copy();env.pop('SSH_AUTH_SOCK',None)
port=43189;url=f'http://127.0.0.1:{port}'
env.update({'OTEL_EXPORTER_OTLP_ENDPOINT':url,'OTEL_EXPORTER_OTLP_LOGS_ENDPOINT':url+'/v1/logs','OTEL_EXPORTER_OTLP_METRICS_ENDPOINT':url+'/v1/metrics','OTEL_EXPORTER_OTLP_TRACES_LIVE':'1'})
with (base/'receiver.log').open('w') as log:
 receiver=subprocess.Popen(['/tmp/collections-perf/greetings/ts-registration/otlpdump','-addr',f'127.0.0.1:{port}','-out',str(base/'telemetry.jsonl')],stdout=log,stderr=log)
 try:
  deadline=time.monotonic()+5
  while True:
   assert receiver.poll() is None,'receiver stopped'
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
   except OSError:
    if time.monotonic()>deadline:raise
    time.sleep(.1)
  with (base/'command.out').open('wb') as out,(base/'command.err').open('wb') as err:
   p=subprocess.run(['/tmp/collections-perf/committed/dagger','--engine','container://dagger-engine.collections-kyle-syntax','check','-l','--all'],cwd=ws,env=env,stdout=out,stderr=err,timeout=180);p.check_returncode()
  assert (base/'command.out').read_bytes()==Path('/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out').read_bytes()
 finally:
  receiver.terminate();receiver.wait(timeout=5)
markers=[]
for line in (base/'telemetry.jsonl').read_text().splitlines():
 e=json.loads(line)
 if e.get('kind')=='log' and 'IMPORT_PERF ' in e.get('body',''):
  for part in e['body'].splitlines():
   if part.startswith('IMPORT_PERF '):markers.append({'span':e['spanId'],**json.loads(part[len('IMPORT_PERF '):])})
(base/'markers.json').write_text(json.dumps(markers,indent=2)+'\n')
print(json.dumps(markers,indent=2),flush=True)
