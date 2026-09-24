from pathlib import Path
import subprocess, time, json, urllib.request
base=Path('/tmp/collections-perf/committed/greetings/batch-qa');base.mkdir(exist_ok=True)
rows=[]
for variant,cli,engine,workspace,port in [
 ('original','/tmp/collections-perf/untouched-pr/dagger','dagger-engine.collections-committed-original-0','/tmp/collections-perf/committed/greetings/warm-workspace-original',6090),
 ('candidate','/tmp/collections-perf/committed/dagger','dagger-engine.collections-committed-candidate-0','/tmp/collections-perf/committed/greetings/warm-workspace-candidate',6091)]:
 for mode in ['list','execute']:
  args=[cli,'--engine','container://'+engine]
  if mode=='execute':
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump') as r:r.read()
   args+=['--profile']
  args+=['check']
  if mode=='list':args+=['-l']
  args+=['go/modules/tests/run','--go-module=.','--go-test=TestSelectGreeting','--go-test=TestFormatResponse']
  t=time.monotonic()
  with (base/(variant+'-'+mode+'.out')).open('wb') as out,(base/(variant+'-'+mode+'.err')).open('wb') as err:
   p=subprocess.run(args,cwd=workspace,stdout=out,stderr=err,timeout=300)
  row={'variant':variant,'mode':mode,'exit_code':p.returncode,'seconds':time.monotonic()-t,'command':args}
  if mode=='execute':
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump') as r:data=r.read()
   (base/(variant+'.wcprof')).write_bytes(data)
   lines=data.splitlines();header=json.loads(lines[0]);strings=header['strings'];events=[json.loads(x) for x in lines[1:]]
   counts={}
   for e in events:
    if e.get('k')=='call_exec':
     name=strings[e.get('c',0)]
     if any(x in name for x in ['GoTest','GoModule']):counts[name]=counts.get(name,0)+1
   row['execution_counts']=counts;row['dropped_events']=header['dropped_events'];row['open_ops']=len(header.get('open_ops',[]))
  rows.append(row);(base/'summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
