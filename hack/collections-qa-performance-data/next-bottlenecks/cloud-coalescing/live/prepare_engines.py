"""Bounded task-owned engine preparation, run only in parent-granted slot."""
from pathlib import Path
import hashlib,json,subprocess,time,urllib.request
B=Path(__file__).resolve().parent
EXPECTED={
 'dagger-engine.collections-disk-abba-1':('6c1c8136c625198bc84bdcd4f1c5f203ed99fd6d1aa6282e0479a81723c2e584','094f77de46e9b5df658f391cc751ebc48a4d3e01a6fdf12db66666927a8e6106'),
 'dagger-engine.collections-disk-abba-2':('e7457765f81a0dde504642bdd20304d48f045d995853e3dcdd2a5c3f85ad3abc','a1b41acdd93b65fd0a3baf3078f70ef51ab1293a0c5526f473e60c57cc875cf5')}
def run(cmd):return subprocess.check_output(cmd,text=True).strip()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
assert sha(B/'engine-100ms')==json.loads((B/'validation.json').read_text())['engine_sha256']
for name,(identity,expected) in EXPECTED.items():
 actual=json.loads(run(['docker','inspect','--format','{"id":{{json .Id}},"mounts":{{json .Mounts}},"image":{{json .Image}}}',name]))
 assert actual['id']==identity and actual['image']=='sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
 assert len(actual['mounts'])==1 and actual['mounts'][0]['Type']=='volume' and actual['mounts'][0]['Name']==name and actual['mounts'][0]['Destination']=='/var/lib/dagger'
 backup=B/('original-'+name.rsplit('-',1)[1]+'-engine')
 assert not backup.exists(),'backup already exists'
 run(['docker','cp',name+':/usr/local/bin/dagger-engine',str(backup)])
 assert sha(backup)==expected,'existing engine does not match recorded task binary'
for name in EXPECTED:run(['docker','stop','--timeout','30',name])
run(['docker','cp',str(B/'engine-100ms'),'dagger-engine.collections-disk-abba-1:/usr/local/bin/dagger-engine'])
rows=[]
for i,name in enumerate(EXPECTED):
 started=time.monotonic();run(['docker','start',name])
 for _ in range(200):
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{6171+i}/debug/pprof/',timeout=1):break
  except OSError:time.sleep(.1)
 else:raise RuntimeError('engine not ready')
 rows.append({'name':name,'start_to_ready_seconds':time.monotonic()-started,'engine_sha256':run(['docker','exec',name,'sha256sum','/usr/local/bin/dagger-engine']).split()[0]})
(B/'engine-startup.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows))
