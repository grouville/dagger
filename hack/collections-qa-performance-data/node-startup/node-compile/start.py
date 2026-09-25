from pathlib import Path
import io,json,hashlib,tarfile,subprocess,urllib.request,time
b=Path('/tmp/collections-perf/half-second/node-compile');blobs=b/'blobs';blobs.mkdir(exist_ok=True)
base=Path('/tmp/collections-perf/prebuilt-ts-sdk/blobs')
manifest=json.loads((base/'e0b4ffc34649759e908bb75b4fedc1dd4d872476c40429871b1a6a01931a380d').read_text())
config=json.loads((base/manifest['config']['digest'].split(':')[1]).read_text())
def save(data):
 k=hashlib.sha256(data).hexdigest();(blobs/k).write_bytes(data);return {'digest':'sha256:'+k,'size':len(data)}
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w') as tar:
 content=(b/'typescript-sdk-runtime').read_bytes();info=tarfile.TarInfo('bin/typescript-sdk-runtime');info.size=len(content);info.mode=0o755;info.mtime=0;tar.addfile(info,io.BytesIO(content))
layer=save(data.getvalue())|{'mediaType':'application/vnd.oci.image.layer.v1.tar'}
config['rootfs']['diff_ids'].append(layer['digest']);config['history'].append({'created_by':'Prototype: persist tsx transforms; load Node directly'})
manifest['config']=save(json.dumps(config,separators=(',',':')).encode())|{'mediaType':'application/vnd.oci.image.config.v1+json'}
manifest['layers'].append(layer);new=save(json.dumps(manifest,separators=(',',':')).encode())
name='dagger-engine.collections-tsx-node-cache';port=6145
for kind in ['container','volume']:assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0
subprocess.run(['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+new['digest'],'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['docker','cp','/tmp/collections-perf/schema-decode/engine',name+':/usr/local/bin/dagger-engine'],check=True)
for d in [base,blobs]:
 for f in d.iterdir():subprocess.run(['docker','cp',str(f),name+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
for i in range(200):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1):break
 except OSError:time.sleep(.1)
else:raise RuntimeError('engine not ready')
(b/'manifest.json').write_text(json.dumps({'engine':name,'port':port,'sdk_manifest':new,'layer':layer},indent=2)+'\n')
print(name,new,flush=True)
