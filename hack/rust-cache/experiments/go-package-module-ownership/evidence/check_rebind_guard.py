from pathlib import Path
import json,os,subprocess,time,urllib.request
root=Path(__file__).parent;base=root.parent;module=Path('/tmp/dagger-go-module-test-name-index')
source=module/'go.dang';original=source.read_bytes()
old='if (moduleRoot != null\n      and moduleLayoutDigest != null\n      and moduleLayoutDigest == tool.lib.moduleLayoutDigest(ws))'
assert old in original.decode()
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
def mode(on):
 with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/reusable-declarations?enabled='+str(on).lower(),data=b''),timeout=20) as r:assert json.load(r)['enabled']==on
with urllib.request.urlopen('http://127.0.0.1:16104/debug/reusable-declarations',timeout=20) as r:saved=json.load(r)['enabled']
rows=[]
try:
 mode(True)
 for label,guard in [('unguarded',False),('guarded',True)]:
  text=original.decode() if guard else original.decode().replace(old,'if (moduleRoot != null)')
  source.write_text(text);(root/(label+'-go.dang')).write_text(text)
  mark=time.monotonic()
  with (root/(label+'-rebind.log')).open('w') as out:p=subprocess.run(['python3',str(base/'local_cli_collector.py'),'check','go-dev:package-layout-rebind-check'],cwd=module,env=env,stdout=out,stderr=subprocess.STDOUT)
  log=(root/(label+'-rebind.log')).read_text()
  row=dict(label=label,guard=guard,exit_code=p.returncode,seconds=time.monotonic()-mark)
  rows.append(row);(root/'rebind-proof.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
  if guard:assert p.returncode==0
  else:assert p.returncode!=0 and 'Go tests in sub:' in log and 'inference error' not in log,log[-2500:]
finally:
 source.write_bytes(original);mode(saved)
