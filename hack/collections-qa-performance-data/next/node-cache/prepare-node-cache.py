from pathlib import Path
import json,hashlib,tarfile,io,subprocess,socket,time
base=Path('/tmp/collections-perf/ts-cache');blobs=base/'node-cache-blobs';blobs.mkdir(exist_ok=True)
p=base/'extracted/runtime/runtime_node.go';s=p.read_text();needle='\t\tWithEnvVariable("NODE_OPTIONS", "--use-openssl-ca").'
assert s.count(needle)==1
s=s.replace(needle,needle+'''\n		WithMountedCache("/root/.cache/dagger-node-compile", dag.CacheVolume("node-compile")).
		WithEnvVariable("NODE_COMPILE_CACHE", "/root/.cache/dagger-node-compile").''')
(base/'runtime_node-cache.go').write_text(s)
# Append an ordinary OCI layer; retain all original SDK layers and content IDs.
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w',format=tarfile.PAX_FORMAT) as tar:
 info=tarfile.TarInfo('runtime/runtime_node.go');info.size=len(s.encode());info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(s.encode()))
def save(data):
 name=hashlib.sha256(data).hexdigest();(blobs/name).write_bytes(data);return {'digest':'sha256:'+name,'size':len(data)}
layer=save(data.getvalue())|{'mediaType':'application/vnd.oci.image.layer.v1.tar'}
config=json.loads((base/'sdk-config.json').read_text());config['rootfs']['diff_ids'].append(layer['digest']);config['history'].append({'created_by':'experimental Node compile cache'})
conf=save(json.dumps(config,separators=(',',':')).encode())|{'mediaType':'application/vnd.oci.image.config.v1+json'}
manifest=json.loads((base/'sdk-manifest.json').read_text());manifest['config']=conf;manifest['layers'].append(layer)
new=save(json.dumps(manifest,separators=(',',':')).encode())
engine='dagger-engine.collections-node-cache';port=6098
for kind in ['container','volume']:
 assert subprocess.run(['docker',kind,'inspect',engine],capture_output=True).returncode!=0,engine+' exists'
subprocess.run(['docker','create','--name',engine,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',engine+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+new['digest'],'localhost/dagger-engine.collections-perf:latest','--extra-debug','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['docker','cp','/tmp/collections-perf/syntax-isolated/engine',engine+':/usr/local/bin/dagger-engine'],check=True)
for f in blobs.iterdir():subprocess.run(['docker','cp',str(f),engine+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
subprocess.run(['docker','start',engine],check=True,stdout=subprocess.DEVNULL)
deadline=time.monotonic()+30
while True:
 try:
  with socket.create_connection(('127.0.0.1',port),timeout=1):break
 except OSError:
  if time.monotonic()>deadline:raise
  time.sleep(.1)
(base/'node-cache-manifest.json').write_text(json.dumps({'engine':engine,'port':port,'sdk_manifest':new,'added_layer':layer,'engine_binary':'/tmp/collections-perf/syntax-isolated/engine'},indent=2)+'\n')
print('Ready',engine,new['digest'],flush=True)
