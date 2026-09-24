from pathlib import Path
import os, subprocess, socket, time, sys, json
os.environ.pop('SSH_AUTH_SOCK',None)
base=Path('/tmp/collections-perf/prebuilt-ts-sdk')
manifest=json.loads((base/'manifest.json').read_text())
expected=Path('/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out').read_bytes()
rows=[]
for variant,port in [('candidate',6118)]:
    name='dagger-engine.collections-prebuilt-cold-profiled'
    for kind in ['container','volume']:
        assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0
    cmd=['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger']
    payload=base if variant=='candidate' else Path('/tmp/collections-perf/ts-runtime-manifest')
    sdk=json.loads((payload/'manifest.json').read_text())
    cmd+=['-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+sdk['sdk_manifest']['digest']]
    cmd+=['localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060']
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['docker','cp',str(base/'engine-profiled') if variant=='candidate' else '/tmp/collections-perf/rebuilt-prototypes/engine',name+':/usr/local/bin/dagger-engine'],check=True)
    if True:
        for f in (payload/'blobs').iterdir():subprocess.run(['docker','cp',str(f),name+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
    subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
    deadline=time.monotonic()+30
    while True:
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=1):break
        except OSError:
            if time.monotonic()>deadline:raise
            time.sleep(.1)
    dest=base/'deep-profile'/variant
    cmd=[sys.executable,'/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','1','--warmups','0','--timeout','600','--output',str(dest),'--wcprof-url',f'http://127.0.0.1:{port}','--cold-profile','--expect-stdout','/tmp/collections-perf/kyle-latest/warm/original-0/run-0.out','--','/tmp/collections-perf/committed/dagger','--engine','container://'+name,'check','-l','--all']
    p=subprocess.run(cmd,cwd='/tmp/collections-perf/normal-baseline/greetings-split',capture_output=True,text=True)
    (dest/'driver.log').write_text(p.stdout+p.stderr)
    result=json.loads((dest/'results.json').read_text())
    correct=(dest/'run-0.out').read_bytes()==expected
    row={'variant':variant,'seconds':result['median_seconds'],'status':p.returncode,'correct':correct};rows.append(row)
    (base/'deep-profile/results.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
    with (dest/'analysis.txt').open('w') as f:subprocess.run(['/tmp/wcprof-analyze','-top','30',str(dest/'runs.wcprof')],stdout=f,check=True)
    p.check_returncode();assert correct
