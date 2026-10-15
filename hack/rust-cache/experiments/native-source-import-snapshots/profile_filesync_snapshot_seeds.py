import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'filesync-snapshot-seeds-profile'
root.mkdir(exist_ok=False)
telemetry=Path('/tmp/rust-cache-oct13-filter/local-receiver/telemetry.jsonl')
fixtures={size:Path(f'/tmp/rust-native-config-entry-{size}-after') for size in ['1026','130','small']}

def debug(route,data=None):
 return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/wcprof/'+route,data=data),timeout=30)
with debug('enabled') as response:assert not json.load(response)['global_enabled']

def invoke(size,label,enabled=False):
 subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n' if enabled else b'off\n',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 source=fixtures[size]
 relative={'1026':'leaf_1023/src/lib.rs','130':'leaf_0127/src/lib.rs','small':'app/src/lib.rs'}[size]
 filename=source/relative
 value=secrets.randbits(48)
 pattern=r'pub fn edited_value\(\) -> u64 \{ \d+ \}' if size=='small' else r'pub const EDIT: u64 = \d+;'
 replacement=f'pub fn edited_value() -> u64 {{ {value} }}' if size=='small' else f'pub const EDIT: u64 = {value};'
 text,count=re.subn(pattern,replacement,filename.read_text());assert count==1
 filename.write_text(text)
 start=time.monotonic()
 with (root/(label+'.log')).open('w') as output:
  result=subprocess.run(['python3',str(base/'local_cli.py'),'check','rust:packages/test' if size=='small' else 'rust:check'],cwd=source,env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276'),stdout=output,stderr=subprocess.STDOUT)
 assert result.returncode==0,label
 return time.monotonic()-start

def spans_since(offset,label):
 end=telemetry.stat().st_size
 assert end-offset<150_000_000,(label,'unexpected telemetry range size',end-offset)
 found=[]
 with telemetry.open('rb') as stream:
  stream.seek(offset)
  while stream.tell()<end:
   raw=stream.readline()
   if not raw.endswith(b'\n'):break
   if b'"spanId"' not in raw:continue
   row=json.loads(raw)
   if row.get('name','').startswith('uploading ') or row.get('name')=='copy':
    found.append({key:row[key] for key in ['name','spanId','parentId','startNs','endNs','traceId']})
 with (root/'telemetry-ranges.jsonl').open('a') as output:output.write(json.dumps(dict(label=label,start=offset,end=end))+'\n')
 completed={(span['traceId'],span['spanId']):span for span in found if span['endNs']>=span['startNs']>0}
 return list(completed.values())

originals={}
summaries={}
try:
 for source in fixtures.values():
  config=source/'dagger.toml';originals[config]=config.read_text()
  text,count=re.subn(r'source = "[^"]+"','source = "/tmp/dagger-rust-config-plan-file-transfer"',originals[config],count=1);assert count==1
  config.write_text(text)
 for size in fixtures:invoke(size,'prepare-'+size)
 for size in fixtures:invoke(size,'prepare-seeded-'+size,True)
 for index,(size,enabled) in enumerate([(size,enabled) for size in ['1026','130','small'] for enabled in [False,True,False,True]]):
  label=f'{index}-{size}-{"seed" if enabled else "full"}'
  debug('enabled',b'on').close()
  with debug('dump') as response:
   while response.read(1048576):pass
  offset=telemetry.stat().st_size
  try:seconds=invoke(size,label,enabled)
  finally:
   debug('enabled',b'off').close()
   with debug('dump') as response,(root/(label+'.ndjson')).open('wb') as output:
    while data:=response.read(1048576):output.write(data)
  with (root/(label+'.ndjson')).open() as stream:header=json.loads(next(stream))
  assert not header['dropped_events'] and not header.get('open_ops'),label
  time.sleep(.2)
  spans=spans_since(offset,label)
  (root/(label+'.filesync-spans.json')).write_text(json.dumps(spans,indent=2)+'\n')
  uploads=[]
  for span in spans:
   if not span['name'].startswith('uploading '):continue
   copies=[item for item in spans if item['name']=='copy' and item['parentId']==span['spanId'] and item['traceId']==span['traceId']]
   uploads.append(dict(path=span['name'].removeprefix('uploading '),upload_ms=(span['endNs']-span['startNs'])/1e6,copy_ms=[(item['endNs']-item['startNs'])/1e6 for item in copies],before_copy_ms=[(item['startNs']-span['startNs'])/1e6 for item in copies]))
  summaries[label]=dict(seconds=seconds,uploads=uploads,wcprof=dict(events=header['event_count'],dropped_events=header['dropped_events'],open_ops=header.get('open_ops',0)))
  (root/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
  print(label,json.dumps(uploads),flush=True)
finally:
 subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 debug('enabled',b'off').close()
 for config,text in originals.items():config.write_text(text)
print('PASS: source import diagnostics; modules restored; wcprof disabled',flush=True)
