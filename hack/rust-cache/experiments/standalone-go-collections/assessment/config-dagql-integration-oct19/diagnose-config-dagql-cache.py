from pathlib import Path
import gzip,json,threading,time,urllib.request
from config_dagql_benchmark_helpers import engine_info,run
out=Path('/tmp/go-collection-upstream-review-oct19')
root=out/'config-dagql-listing-fixture'
info=json.loads((out/'config-dagql-engines.json').read_text())['candidate']
engine=engine_info(info['name'],info['runner'],info['debug'])
test=root/'pkg_000/value_test.go'
original=test.read_bytes()
name='TestCacheDiagnostic'+str(time.time_ns())
records={};errors=[]
stop=threading.Event()
def capture():
 try:
  captures=[]
  index=0
  while not stop.wait(1):
   tick=time.time_ns()
   with urllib.request.urlopen(info['debug']+'/debug/dagql/cache',timeout=90) as response:
    data=response.read()
   path=out/('config-dagql-live-cache-'+str(index)+'.json.gz')
   path.write_bytes(gzip.compress(data,mtime=0))
   snapshot=json.loads(data)
   entries=[entry for group in ['completed_arbitrary_calls','ongoing_arbitrary_calls'] for entry in snapshot.get(group,[]) if entry.get('call_key','').startswith('workspace.git-client-declarations:')]
   captures.append(dict(start_unix_ns=tick, captured_at_time=snapshot.get('captured_at_time'),active_sessions=len(snapshot.get('session_results',[])),entries=entries,path=str(path)))
   records['captures']=captures
   records['entries']=entries
   if entries: break
   index+=1
 except Exception as error: errors.append(str(error))

try:
 test.write_bytes(original.replace(b'func TestValue(',('func '+name+'(').encode(),1))
 thread=threading.Thread(target=capture)
 thread.start()
 metrics,text,log=run('config-dagql-live-cache-observed',root,['check','--module','go','--check','test','--list','--all'],engine)
 stop.set()
 thread.join(timeout=120)
 rows=[line.split()[1:3] for line in text.splitlines() if line.split() and line.split()[0]=='go']
 assert metrics['cleanup_successful'] and len(rows)==16 and ['pkg_000',name] in rows,(metrics,log)
 result=dict(profiling_or_snapshot=True,excluded_from_timing=True,metrics=metrics,cache=records,errors=errors,log=log)
 (out/'config-dagql-live-cache-result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(entries=records.get('entries'),errors=errors)),flush=True)
finally:
 test.write_bytes(original)
