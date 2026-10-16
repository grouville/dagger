import base64,json,os,secrets,urllib.request
from pathlib import Path
url='http://127.0.0.1:'+os.environ['DAGGER_SESSION_PORT']+'/query'
auth=base64.b64encode((os.environ['DAGGER_SESSION_TOKEN']+':').encode()).decode()
root=Path('/tmp/rust-cache-sipsma-review/containerd-root-dedup-validation');root.mkdir(exist_ok=True)
results=[]
def request(query):
 req=urllib.request.Request(url,data=json.dumps({'query':query}).encode(),headers={'Content-Type':'application/json','Authorization':'Basic '+auth})
 with urllib.request.urlopen(req,timeout=180) as response:return json.load(response)
def execute(query):
 r=request(query)
 if r.get('errors'):raise RuntimeError(r['errors'])
 return r['data']
def text(s):return json.dumps(s)
execute('{serveModule(address:".")}')
source=execute('{host{directory(path:"/tmp/rust-native-config-entry-130-before",exclude:[".git","target","dagger.toml","dagger.lock"]){id}}}')['host']['directory']['id']
key='containerd-root-dedup-validation-'+secrets.token_hex(5)
image='rust:1.77-bookworm@sha256:83101f6985c93e1e6501b3375de188ee3d2cbb89968bcc91611591f9f447bd42'
def collect():
 req=urllib.request.Request('http://127.0.0.1:16104/debug/snapshot-collection?action=collect',data=b'')
 with urllib.request.urlopen(req,timeout=120) as response: assert json.load(response)['seconds']>=0
def compile(s,label,hits,error=False):
 q='{rust(image:'+text(image)+',locked:true,cacheKey:'+text(key)+'){nativeCheck(source:'+text(s)+'){actions hits}}}'
 r=request(q)
 if error:
  assert r.get('errors'),r
  message='\n'.join(e['message'] for e in r['errors'])
  assert 'exit code: 1' in message,message
  results.append(dict(label=label,rejected=True));(root/(label+'-error.txt')).write_text(message)
 else:
  if r.get('errors'):raise RuntimeError(r['errors'])
  v=r['data']['rust']['nativeCheck'];assert v==dict(actions=130,hits=hits),(label,v,hits)
  results.append(dict(label=label,**v))
 (root/'results.json').write_text(json.dumps(results,indent=2)+'\n');print('PASS',label,results[-1],flush=True)
 collect()
compile(source,'empty-project-cache',0)
compile(source,'same-source',130)
contents=execute('{node(id:'+text(source)+'){...on Directory{file(path:"leaf_0127/src/lib.rs"){contents}}}}')['node']['file']['contents']
import re
new,n=re.subn(r'pub const EDIT: u64 = \d+;',f'pub const EDIT: u64 = {secrets.randbits(48)};',contents);assert n==1
def changed(contents):
 return execute('{node(id:'+text(source)+'){...on Directory{withNewFile(path:"leaf_0127/src/lib.rs",contents:'+text(contents)+'){id}}}}')['node']['withNewFile']['id']
valid=changed(new);compile(valid,'used-source-edit',128)
compile(changed('this is not valid Rust'), 'invalid-source',0,error=True)
compile(valid,'repair-and-reuse',130)
compile(source,'revert-and-reuse',130)
