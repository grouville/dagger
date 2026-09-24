from pathlib import Path
import io, json, hashlib, tarfile, subprocess, socket, time
base=Path('/tmp/collections-perf/ts-runtime-manifest');blobs=base/'blobs';blobs.mkdir(exist_ok=True)
original=Path('/tmp/collections-perf/ts-cache')
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w',format=tarfile.PAX_FORMAT) as tar:
    for name,content in [('runtime/.wh.dagger.json',b''),('runtime/dagger-module.toml',Path('/home/dagger/dag/sdk/typescript/runtime/dagger-module.toml').read_bytes())]:
        info=tarfile.TarInfo(name);info.size=len(content);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(content))
def save(data):
    name=hashlib.sha256(data).hexdigest();(blobs/name).write_bytes(data);return {'digest':'sha256:'+name,'size':len(data)}
layer=save(data.getvalue())|{'mediaType':'application/vnd.oci.image.layer.v1.tar'}
config=json.loads((original/'sdk-config.json').read_text());config['rootfs']['diff_ids'].append(layer['digest']);config['history'].append({'created_by':'Use committed TypeScript SDK runtime bindings'})
conf=save(json.dumps(config,separators=(',',':')).encode())|{'mediaType':'application/vnd.oci.image.config.v1+json'}
manifest=json.loads((original/'sdk-manifest.json').read_text());manifest['config']=conf;manifest['layers'].append(layer)
new=save(json.dumps(manifest,separators=(',',':')).encode())
engine='dagger-engine.collections-ts-runtime-manifest';port=6110
for kind in ['container','volume']:
    assert subprocess.run(['docker',kind,'inspect',engine],capture_output=True).returncode!=0
subprocess.run(['docker','create','--name',engine,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',engine+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+new['digest'],'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060'],check=True)
subprocess.run(['docker','cp','/tmp/collections-perf/rebuilt-prototypes/engine',engine+':/usr/local/bin/dagger-engine'],check=True)
for f in blobs.iterdir():subprocess.run(['docker','cp',str(f),engine+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
subprocess.run(['docker','start',engine],check=True)
deadline=time.monotonic()+30
while True:
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=1):break
    except OSError:
        if time.monotonic()>deadline:raise
        time.sleep(.1)
(base/'manifest.json').write_text(json.dumps({'engine':engine,'port':port,'sdk_manifest':new,'added_layer':layer,'binary':'/tmp/collections-perf/rebuilt-prototypes/engine'},indent=2)+'\n')
print(new['digest'],flush=True)
