from pathlib import Path
import json,subprocess,urllib.request,time
base=Path('/tmp/collections-perf/schema-decode');payload=Path('/tmp/collections-perf/prebuilt-ts-sdk')
name='dagger-engine.collections-schema-decode';port=6143
for kind in ['container','volume']:
 assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0
manifest=json.loads((payload/'manifest.json').read_text())['sdk_manifest']['digest']
subprocess.run(['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+manifest,'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['docker','cp',str(base/'engine'),name+':/usr/local/bin/dagger-engine'],check=True)
for f in (payload/'blobs').iterdir():
 subprocess.run(['docker','cp',str(f),name+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
for i in range(100):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=2):break
 except OSError:time.sleep(.1)
else:raise RuntimeError('engine did not start')
print(name,port)

subprocess.run(["docker","start","dagger-engine.collections-public-refs"],check=True)
