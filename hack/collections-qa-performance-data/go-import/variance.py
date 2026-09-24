"""Repeat identical cold engines while sampling host pressure; no builds run alongside."""
from pathlib import Path
import os, subprocess, time, sys, json, urllib.request, threading
os.environ.pop('SSH_AUTH_SOCK', None)
base=Path('/tmp/collections-perf/go-import')
payload=Path('/tmp/collections-perf/prebuilt-ts-sdk')
expected=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt')
rows=[]
def sample_host():
    value={'time_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'load':os.getloadavg()}
    for name in ['stat','meminfo','vmstat','diskstats','pressure/cpu','pressure/io','pressure/memory']:
        value[name]=Path('/proc',name).read_text()
    value['cpu_frequency_khz']={p.parent.parent.name:p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu[0-9]*/cpufreq/scaling_cur_freq')}
    return value
for i in range(3):
    label=f'quiet-{i}';port=6127+i
    name='dagger-engine.collections-go-import-'+label
    for kind in ['container','volume']:
        assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0
    cmd=['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger','-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+json.loads((payload/'manifest.json').read_text())['sdk_manifest']['digest'],'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060']
    subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['docker','cp',str(base/'engine'),name+':/usr/local/bin/dagger-engine'],check=True)
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
    dest=base/'variance'/label;dest.mkdir(parents=True)
    cmd=[sys.executable,'/home/dagger/dag/hack/bench-artifact-discovery.py','--runs','1','--warmups','0','--timeout','600','--output',str(dest),'--wcprof-url',f'http://127.0.0.1:{port}','--cold-profile','--expect-stdout',str(expected),'--','/tmp/collections-perf/committed/dagger','--engine','container://'+name,'check','-l','--all']
    stop=threading.Event()
    def sampler():
        with (dest/'host-samples.jsonl').open('w') as out:
            while True:
                out.write(json.dumps(sample_host())+'\n');out.flush()
                if stop.wait(.25):break
    thread=threading.Thread(target=sampler);thread.start()
    try:
        p=subprocess.run(cmd,cwd='/tmp/collections-perf/normal-baseline/greetings-split',capture_output=True,text=True)
    finally:
        stop.set();thread.join()
    (dest/'driver.log').write_text(p.stdout+p.stderr)
    result=json.loads((dest/'results.json').read_text())
    with (dest/'runs.wcprof').open() as f:
        h=json.loads(next(f));strings=h['strings'];ev=[json.loads(x) for x in f]
    phases=[{'class':strings[x.get('c',0)],'ident':strings[x.get('i',0)],'seconds':(x.get('d',0)-x.get('s',0))/1e9,'parent':x.get('p'),'id':x.get('id')} for x in ev if strings[x.get('c',0)].startswith(('builtinImage.','image.'))]
    (dest/'phases.json').write_text(json.dumps(phases,indent=2)+'\n')
    row={'variant':label,'seconds':result['median_seconds'],'go_import_seconds':next(x['seconds'] for x in phases if x['class']=='builtinImage.importRootfs' and x['ident']=='sha256:a5a4214938de6b898267ee413c8b8f6580a08b38ac9db400742a1c934799cc70'),'status':p.returncode,'correct':(dest/'run-0.out').read_bytes()==expected.read_bytes(),'dropped_events':h['dropped_events']}
    rows.append(row)
    (base/'variance/summary.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(row),flush=True)
    with (dest/'analysis.txt').open('w') as out:subprocess.run(['/tmp/wcprof-analyze','-top','20',str(dest/'runs.wcprof')],stdout=out,check=True)
    p.check_returncode();assert row['correct']
