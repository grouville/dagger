import collections
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base=Path('/tmp/rust-cache-sipsma-review');root=base/'rust-metadata-expanded-profile';root.mkdir(exist_ok=False)
variants={'original':'/tmp/dagger-rust-config-plan-file-transfer','prepared':'/tmp/dagger-rust-metadata-toolchain-only','linear':'/tmp/dagger-rust-metadata-toolchain'}
fixtures={size:Path(f'/tmp/rust-native-config-entry-{size}-after') for size in ['1026','small']}

def debug(route,data=None):return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/wcprof/'+route,data=data),timeout=30)
with debug('enabled') as response:assert not json.load(response)['global_enabled']

def invoke(size,variant,label):
 source=fixtures[size];config=source/'dagger.toml'
 text,count=re.subn(r'source = "[^"]+"',f'source = "{variants[variant]}"',originals[config],count=1);assert count==1;config.write_text(text)
 filename=source/('leaf_1023/src/lib.rs' if size=='1026' else 'app/src/lib.rs');value=secrets.randbits(48)
 pattern=r'pub const EDIT: u64 = \d+;' if size=='1026' else r'pub fn edited_value\(\) -> u64 \{ \d+ \}'
 replacement=f'pub const EDIT: u64 = {value};' if size=='1026' else f'pub fn edited_value() -> u64 {{ {value} }}'
 text,count=re.subn(pattern,replacement,filename.read_text());assert count==1;filename.write_text(text)
 start=time.monotonic()
 with (root/(label+'.log')).open('w') as output:
  result=subprocess.run(['python3',str(base/'local_cli.py'),'check','--list','--all','rust:packages/check'],cwd=source,env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276'),stdout=output,stderr=subprocess.STDOUT,timeout=60)
 assert result.returncode==0,label
 return time.monotonic()-start

originals={source/'dagger.toml':(source/'dagger.toml').read_text() for source in fixtures.values()}
summaries={}
try:
 for size in fixtures:
  for variant in variants:invoke(size,variant,f'prepare-{size}-{variant}')
 for size in fixtures:
  for index,variant in enumerate(['original','prepared','linear','linear','prepared','original']):
   label=f'{size}-{index}-{variant}'
   debug('enabled',b'on').close()
   with debug('dump') as response:
    while response.read(1048576):pass
   try:seconds=invoke(size,variant,label)
   finally:
    debug('enabled',b'off').close()
    with debug('dump') as response,(root/(label+'.ndjson')).open('wb') as output:
     while data:=response.read(1048576):output.write(data)
   with (root/(label+'.ndjson')).open() as stream:
    header=json.loads(next(stream));names=header['strings'];ops=[dict(op,cls=names[op.get('c',0)]) for op in map(json.loads,stream) if op['e']=='op']
   assert not header['dropped_events'] and not header.get('open_ops'),label
   assert any(op['k']=='call_exec' and op['cls'].endswith('.packages') for op in ops),(label,'package discovery did not execute')
   classes=collections.defaultdict(lambda:dict(count=0,total_ms=0))
   for op in ops:
    row=classes[op['k']+' '+op['cls']];row['count']+=1;row['total_ms']+=(op['d']-op['s'])/1e6
   summaries[label]=dict(seconds=seconds,classes=dict(classes),events=header['event_count'],dropped_events=header['dropped_events'],open_ops=header.get('open_ops',0))
   (root/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
   print(label,'seconds',round(seconds,3),'HTTP',[(key,value['count']) for key,value in classes.items() if 'http' in key.lower() and key.startswith('call_exec ')],flush=True)
finally:
 debug('enabled',b'off').close()
 for config,text in originals.items():config.write_text(text)
print('PASS: profiles, original configs restored, wcprof off',flush=True)
