"""Serial A/B extraction benchmarks; no builds or tests during measured runs."""
from pathlib import Path
import os, subprocess, time, sys, json, urllib.request, threading, hashlib
os.environ.pop('SSH_AUTH_SOCK', None)
base=Path('/tmp/collections-perf/tar-parent-cache')
payload=Path('/tmp/collections-perf/prebuilt-ts-sdk')
manifest=json.loads((payload/'manifest.json').read_text())['sdk_manifest']['digest']
expected=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt')
mode=sys.argv[1] if len(sys.argv)>1 else 'isolated'
first_port={'isolated':6130,'full':6134,'balanced':6138}[mode]
rows=[]
def host():
    return {'time_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),**{name:Path('/proc',name).read_text() for name in ['stat','meminfo','vmstat','diskstats','pressure/cpu','pressure/io','pressure/memory']}}
for i,(label,candidate) in enumerate([('control-0',False),('candidate-0',True),('candidate-1',True),('control-1',False)]):
    port=first_port+i
    name='dagger-engine.collections-tar-parent-'+mode+'-'+label
    for kind in ['container','volume']:
        assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0
    cmd=['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+manifest,'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060']
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
    binary=base/'engine' if candidate else Path('/tmp/collections-perf/go-import/engine')
    subprocess.run(['docker','cp',str(binary),name+':/usr/local/bin/dagger-engine'],check=True)
    for f in (payload/'blobs').iterdir():
        subprocess.run(['docker','cp',str(f),name+':/usr/local/share/dagger/content/blobs/sha256/'+f.name],check=True)
    subprocess.run(['docker','start',name],check=True,stdout=subprocess.DEVNULL)
    deadline=time.monotonic()+30
    while True:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=2):break
        except OSError:
            if time.monotonic()>deadline:raise
            time.sleep(.1)
    dest=base/mode/label;dest.mkdir(parents=True)
    cmd=[sys.executable,'/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','1','--warmups','0','--timeout','600','--output',str(dest),'--wcprof-url',f'http://127.0.0.1:{port}','--cold-profile']
    if mode!='isolated':cmd+=['--expect-stdout',str(expected)]
    cmd+=['--','/tmp/collections-perf/committed/dagger','--engine','container://'+name]
    if mode=='isolated':cmd+=['api','query','-M','--doc','/tmp/collections-perf/go-import/import.graphql']
    else:cmd+=['check','-l','--all']
    stop=threading.Event()
    def sample():
        with (dest/'host-samples.jsonl').open('w') as out:
            while True:
                out.write(json.dumps(host())+'\n');out.flush()
                if stop.wait(.25):break
    thread=threading.Thread(target=sample);thread.start()
    try:
        p=subprocess.run(cmd,cwd='/tmp' if mode=='isolated' else '/tmp/collections-perf/normal-baseline/greetings-split',capture_output=True,text=True)
    finally:
        stop.set();thread.join()
    (dest/'driver.log').write_text(p.stdout+p.stderr)
    result=json.loads((dest/'results.json').read_text())
    with (dest/'runs.wcprof').open() as f:
        h=json.loads(next(f));strings=h['strings'];events=[json.loads(x) for x in f]
    phases=[{'class':strings[x.get('c',0)],'ident':strings[x.get('i',0)],'seconds':(x.get('d',0)-x.get('s',0))/1e9,'parent':x.get('p'),'id':x.get('id')} for x in events if strings[x.get('c',0)].startswith(('builtinImage.','image.'))]
    (dest/'phases.json').write_text(json.dumps(phases,indent=2)+'\n')
    stdout=(dest/'run-0.out').read_bytes()
    correct=b'go1.26' in stdout if mode=='isolated' else stdout==expected.read_bytes()
    row={'variant':label,'engine':name,'seconds':result['median_seconds'],'go_import_seconds':next((x['seconds'] for x in phases if x['class']=='builtinImage.importRootfs' and x['ident']=='sha256:a5a4214938de6b898267ee413c8b8f6580a08b38ac9db400742a1c934799cc70'),None),'status':p.returncode,'correct':correct,'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'dropped_events':h['dropped_events'],'open_ops':h.get('open_ops')}
    rows.append(row)
    (base/mode/'summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
    with (dest/'analysis.txt').open('w') as out:subprocess.run(['/tmp/wcprof-analyze','-top','25',str(dest/'runs.wcprof')],stdout=out,check=True)
    p.check_returncode();assert correct
    # Keep one full-app pair alive for warm/edit validation, preserve every volume.
    if mode in ('isolated','balanced') or label.endswith('-1'):
        subprocess.run(['docker','stop','-t','10',name],check=True,stdout=subprocess.DEVNULL)
