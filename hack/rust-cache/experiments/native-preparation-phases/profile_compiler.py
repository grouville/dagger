import json,os,re,secrets,shutil,subprocess,time,urllib.request
from pathlib import Path
base=Path('/tmp/rust-cache-sipsma-review')
root=base/'native-bulk-compile-phase-profile-complete';root.mkdir(exist_ok=False)
telemetry=Path('/tmp/rust-cache-oct13-filter/local-receiver/telemetry.jsonl')
fixtures={kind:Path('/tmp/rust-native-bulk-digests-'+size+'-after') for kind,size in [('many','1026'),('root','130'),('small','small')]}

def debug(route,data=None):return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16103/debug/wcprof/'+route,data=data),timeout=30)
with debug('enabled') as f:assert not json.load(f)['global_enabled']

def extract(start,label):
 deadline=time.monotonic()+5
 while True:
  found=[]
  end=telemetry.stat().st_size
  with telemetry.open('rb') as f:
   f.seek(start)
   data=f.read(end-start)
  for line in data.splitlines(keepends=True):
   if not line.endswith(b'\n') or b'RUST_COMPILE_DIAGNOSTIC ' not in line:continue
   row=json.loads(line)
   def walk(value):
    if isinstance(value,str) and value.startswith('RUST_COMPILE_DIAGNOSTIC '):
     found.append(json.loads(value.split(' ',1)[1]))
    elif isinstance(value,dict):
     for v in value.values():walk(v)
    elif isinstance(value,list):
     for v in value:walk(v)
   walk(row)
  if found:break
  assert time.monotonic()<deadline,(label,'diagnostic log did not arrive')
  time.sleep(.05)
 (root/(label+'.phases.json')).write_text(json.dumps(found,indent=2)+'\n')
 with (root/'telemetry-ranges.jsonl').open('a') as f:f.write(json.dumps(dict(label=label,start=start,end=end,records=len(found)))+'\n')
 for profile in found:
  print(label,'compile_ms',round(profile['total_ms'],2),'phases',[(e['phase'],round(e['duration_ms'],2)) for e in profile['events'] if e['phase']!='graphql.request'],flush=True)

def run(kind,label,edit_kind=None,capture=False):
 src=fixtures[kind]
 if edit_kind:
  rel='app/src/lib.rs' if kind=='small' else ('shared/src/lib.rs' if edit_kind=='shared' else ('leaf_0127/src/lib.rs' if kind=='root' else 'leaf_1023/src/lib.rs'))
  pattern=r'pub fn edited_value\(\) -> u64 \{ \d+ \}' if kind=='small' else r'pub const EDIT: u64 = \d+;'
  value=secrets.randbits(48)
  replacement=f'pub fn edited_value() -> u64 {{ {value} }}' if kind=='small' else f'pub const EDIT: u64 = {value};'
  p=src/rel;text,n=re.subn(pattern,replacement,p.read_text());assert n==1;p.write_text(text)
 if capture:
  debug('enabled',b'on').close()
  with debug('dump') as f:
   while f.read(1048576):pass
 offset=telemetry.stat().st_size
 try:
  with (root/(label+'.log')).open('w') as f:
   result=subprocess.run(['python3',str(base/'local_cli.py'),'check','rust:packages/test' if kind=='small' else 'rust:check'],cwd=src,env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16275'),stdout=f,stderr=subprocess.STDOUT)
  assert not result.returncode,(label,result.returncode)
 finally:
  if capture:
   debug('enabled',b'off').close()
   with debug('dump') as f,(root/(label+'.ndjson')).open('wb') as out:
    while b:=f.read(1048576):out.write(b)
   with (root/(label+'.ndjson')).open() as f:h=json.loads(next(f))
   assert not h['dropped_events'] and not h.get('open_ops'),h
 extract(offset,label)
originals = {}
try:
 for fixture in fixtures.values():
  config = fixture/'dagger.toml'
  originals[config] = config.read_text()
  text,count = re.subn(r'source = "[^"]+"', 'source = "/tmp/dagger-rust-bulk-phase-profile"', originals[config], count=1)
  assert count==1
  config.write_text(text)
 for i in range(2):
  for kind in fixtures:run(kind,f'prepare-{i}-{kind}','leaf')
 for label,kind,edit in [('large-0','many','leaf'),('root-0','root','leaf'),('collection-0','small','leaf'),('large-1','many','leaf'),('root-shared','root','shared'),('collection-1','small','leaf')]:run(kind,label,edit,True)
finally:
 for config,text in originals.items():config.write_text(text)
print('PASS: fresh edited Rust module compile phases, grouped hashes and local telemetry',flush=True)
