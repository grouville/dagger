from pathlib import Path
import argparse, concurrent.futures, hashlib, json, os, subprocess, threading, time, urllib.request

B = Path('/tmp/collections-perf/post-rebase-io')
REPO = Path('/home/dagger/dag')
CLI = Path('/tmp/collections-perf/rebase-main/dagger')
WANT = (REPO/'hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
ENV = dict(os.environ)
ENV.pop('SSH_AUTH_SOCK', None)

def run(args):
    return subprocess.check_output(args, text=True).strip()

def fields(path):
    return {s[0].rstrip(':'): int(s[1]) for s in map(str.split, Path(path).read_text().splitlines()) if len(s)>1}

def psi(path):
    return {s.split()[0]: int(s.rsplit('=',1)[1]) for s in Path(path).read_text().splitlines()}

def io_stats(path):
    return {s[0]: {k:int(v) for k,v in (x.split('=') for x in s[1:])} for s in map(str.split,Path(path).read_text().splitlines())}

def cgroup(name):
    pid=run(['docker','inspect','--format','{{.State.Pid}}',name])
    cg=Path('/sys/fs/cgroup')/Path('/proc',pid,'cgroup').read_text().split('::')[1].strip().lstrip('/')
    return cg.parent if cg.name=='init' else cg

def sample(cg):
    vm=fields('/proc/vmstat');mem=fields('/proc/meminfo')
    return {
        'unix_ns':time.time_ns(),'mono_ns':time.monotonic_ns(),
        'host_psi':{k:psi('/proc/pressure/'+k) for k in ['io','cpu','memory']},
        'vmstat':{k:vm[k] for k in ['pswpin','pswpout','nr_dirty','nr_writeback','pgmajfault']},
        'meminfo_kib':{k:mem[k] for k in ['MemAvailable','Dirty','Writeback','SwapFree']},
        'diskstats':{s[2]:list(map(int,s[3:])) for s in map(str.split,Path('/proc/diskstats').read_text().splitlines()) if s[2].startswith('nvme')},
        'engine_psi':{k:psi(cg/(k+'.pressure')) for k in ['io','cpu','memory']},
        'engine_io':io_stats(cg/'io.stat'),
        'engine_memory':int((cg/'memory.current').read_text()),
        'engine_swap':int((cg/'memory.swap.current').read_text()),
        'system_io':{str(p.parent.relative_to('/sys/fs/cgroup')):io_stats(p) for p in Path('/sys/fs/cgroup/system.slice').glob('*/io.stat')},
    }

def delta_io(a,b):
    return {dev:{k:b[dev][k]-a.get(dev,{}).get(k,0) for k in b[dev]} for dev in b}

def measure(name, port, ws, label, core=False, profile=False):
    dest=B/name/label;dest.mkdir(parents=True,exist_ok=False)
    cmd=[str(CLI),'--engine','container://'+name]
    if profile:cmd+=['--profile']
    cmd+=['-m','core','api','query','--doc','/tmp/collections-perf/discovery-next/cli-floor/query.graphql'] if core else ['check','-l','--all']
    cg=cgroup(name); samples=[];stop=threading.Event()
    def sampler():
        while not stop.is_set():
            samples.append(sample(cg))
            stop.wait(.25)
    # Keep samples in memory until after the timed command to avoid our own writeback.
    samples.append(sample(cg));thread=threading.Thread(target=sampler);thread.start()
    start=time.monotonic()
    try:
        with (dest/'stdout.txt').open('wb') as out,(dest/'stderr.txt').open('wb') as err:
            p=subprocess.Popen(cmd,cwd=ws,env=ENV,stdout=out,stderr=err)
            timer=threading.Timer(300,p.terminate);timer.start()
            try:status=p.wait()
            finally:timer.cancel();timer.join()
        elapsed=time.monotonic()-start
    finally:stop.set();thread.join()
    samples.append(sample(cg))
    output=(dest/'stdout.txt').read_bytes()
    correct=(json.loads(output)=={'__typename':'Query'}) if core and status==0 else output==WANT
    a,b=samples[0],samples[-1];duration=(b['mono_ns']-a['mono_ns'])/1e9
    row={'label':label,'engine':name,'command':cmd,'cwd':str(ws),'seconds':elapsed,'status':status,'correct':correct,'profiled':profile,
         'stdout_sha256':hashlib.sha256(output).hexdigest(),'sample_seconds':duration,
         'host_io_full_seconds':(b['host_psi']['io']['full']-a['host_psi']['io']['full'])/1e6,
         'engine_io_full_seconds':(b['engine_psi']['io']['full']-a['engine_psi']['io']['full'])/1e6,
         'engine_io':delta_io(a['engine_io'],b['engine_io']),
         'swap_in_bytes':(b['vmstat']['pswpin']-a['vmstat']['pswpin'])*os.sysconf('SC_PAGE_SIZE'),
         'swap_out_bytes':(b['vmstat']['pswpout']-a['vmstat']['pswpout'])*os.sysconf('SC_PAGE_SIZE')}
    (dest/'samples.json').write_text(json.dumps(samples,separators=(',',':'))+'\n')
    (dest/'result.json').write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row),flush=True)
    if profile:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/wcprof/dump',timeout=60) as r:(dest/'runs.wcprof').write_bytes(r.read())
    assert status==0 and correct, str(dest)
    return row

def start(name,port,standard=False,binary=None,image=None):
    for kind in ['container','volume']:
        assert subprocess.run(['docker',kind,'inspect',name],capture_output=True).returncode!=0,name+' exists'
    command=['docker','create','--name',name,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger']
    meta={'source':run(['git','-C',str(REPO),'rev-parse','HEAD']),'standard_payload':standard,'image':run(['docker','image','inspect','--format','{{.Id}}','localhost/dagger-engine.collections-perf:latest'])}
    if not standard:
        manifest=json.loads(Path('/tmp/collections-perf/half-second/node-compile/manifest.json').read_text())['sdk_manifest']['digest']
        command+=['-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST='+manifest];meta['sdk_manifest']=manifest
    command+=[image or 'localhost/dagger-engine.collections-perf:latest','--debugaddr=0.0.0.0:6060']
    run(command)
    binary=Path(binary) if binary else (Path('/tmp/collections-perf/rebase-main/engine') if standard else B/'engine')
    if image:
        meta['image']=run(['docker','image','inspect','--format','{{.Id}}',image])
        meta['packaged_image']=True
    else:
        run(['docker','cp',str(binary),name+':/usr/local/bin/dagger-engine']);meta['engine_binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
    if not standard and not image:
        for folder in ['/tmp/collections-perf/prebuilt-ts-sdk/blobs','/tmp/collections-perf/half-second/node-compile/blobs']:
            for p in Path(folder).iterdir():run(['docker','cp',str(p),name+':/usr/local/share/dagger/content/blobs/sha256/'+p.name])
    run(['docker','start',name])
    for i in range(200):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/debug/pprof/',timeout=1):break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('engine not ready')
    dest=B/name;dest.mkdir(exist_ok=True);(dest/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('name');ap.add_argument('--port',type=int,default=6160);ap.add_argument('--standard',action='store_true');ap.add_argument('--binary');ap.add_argument('--image');ap.add_argument('--warm',type=int,default=5);ap.add_argument('--profile-cold',action='store_true');args=ap.parse_args()
    ws=Path('/tmp/collections-perf/normal-baseline')/('greetings-committed' if args.standard else 'greetings-split')
    try:
        start(args.name,args.port,args.standard,args.binary,args.image)
        measure(args.name,args.port,ws,'cold',profile=args.profile_cold)
        for i in range(args.warm):measure(args.name,args.port,ws,f'warm-{i}')
        if args.warm:
            for i in range(3):measure(args.name,args.port,ws,f'core-{i}',core=True)
            measure(args.name,args.port,ws,'warm-profile',profile=True)
    finally:
        p=subprocess.run(['docker','stop','--timeout','30',args.name],capture_output=True,text=True)
        print('stopped',args.name,p.returncode,flush=True)
