from pathlib import Path
import subprocess,json,urllib.request,time
b=Path('/tmp/collections-perf/discovery-next')
meta=json.loads(Path('/tmp/collections-perf/half-second/node-compile/manifest.json').read_text())
name='dagger-engine.collections-artifact-schema-fork';port=6146
for kind in ['container','volume']:assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0
subprocess.run(['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+meta['sdk_manifest']['digest'],'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['docker','cp',str(b/'engine'),name+':/usr/local/bin/dagger-engine'],check=True)
for d in [Path('/tmp/collections-perf/prebuilt-ts-sdk/blobs'),Path('/tmp/collections-perf/half-second/node-compile/blobs')]:
 for f in d.iterdir():subprocess.run(['docker','cp',str(f),name+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
for i in range(200):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1):break
 except OSError:time.sleep(.1)
else:raise RuntimeError('engine not ready')
(b/'manifest.json').write_text(json.dumps({'engine':name,'port':port,'sdk_manifest':meta['sdk_manifest']},indent=2)+'\n')
print(name,flush=True)
