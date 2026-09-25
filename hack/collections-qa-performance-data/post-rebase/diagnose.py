from pathlib import Path
import sys,subprocess,time,re,json,urllib.request
sys.path.insert(0,'/tmp/collections-perf/post-rebase-io')
import run as lab
name='dagger-engine.collections-complete-io-0';port=6163
variant=sys.argv[1];binary=sys.argv[2]
lab.run(['docker','stop','--timeout','30',name])
lab.run(['docker','cp',binary,name+':/usr/local/bin/dagger-engine'])
lab.run(['docker','start',name])
for i in range(100):
 try:
  urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1).close();break
 except OSError:time.sleep(.1)
for i in range(4):
 start=str(time.time())
 row=lab.measure(name,port,Path('/tmp/collections-perf/normal-baseline/greetings-split'),f'{variant}-{i}')
 logs=subprocess.run(['docker','logs','--since',start,name],capture_output=True,text=True)
 lines=[s for s in (logs.stdout+logs.stderr).splitlines() if s.startswith('CLOUD_BATCH ') or ('shutdown drain phase done' in s and 'isMainClient=true' in s)]
 (lab.B/name/f'{variant}-{i}'/'cloud-timings.txt').write_text('\n'.join(lines)+'\n')
 batches=[dict((k,int(v) if v.isdecimal() else v) for k,v in re.findall(r'(\w+)=(\w+)',s)) for s in lines if s.startswith('CLOUD_BATCH')]
 print(json.dumps({'variant':variant,'run':i,'seconds':row['seconds'],'exports':len(batches),'records':sum(x['records'] for x in batches),'payloads':sum(x['payloads'] for x in batches),'payload_batches':sum(x['payloads']>0 for x in batches),'payload_max_batch':max((x['payloads'] for x in batches),default=0),'max_body_bytes':max((x['body_bytes'] for x in batches),default=0),'export_seconds':sum(x['export_us'] for x in batches)/1e6,'failed':sum(x['failed']=='true' for x in batches)}),flush=True)
