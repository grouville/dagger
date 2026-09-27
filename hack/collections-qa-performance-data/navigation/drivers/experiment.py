"""Matched engines for schema and syntax allocation changes; explicit run modes.

No existing engine is changed. Only owned containers created by prepare are used.
The first expanded listing uses a fresh Dagger volume, not a cold host page cache.
Ordinary Cloud export is enabled only by the separate production action.
"""
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError, URLError
import argparse, hashlib, json, os, re, shutil, signal, socket, statistics, subprocess, threading, time

LAB = Path(__file__).resolve().parent
REPO = Path('/home/dagger/dag')
SDK = Path('/tmp/collections-perf/sdk-edit-audit')
CLI = Path('/tmp/collections-perf/attachables-lifetime/dagger-attachables')
VARIANTS = ('base', 'interface', 'combined')
OWNER = 'collections-engine-allocation-round2'
HTTP = build_opener(ProxyHandler({}))
WANT = (REPO/'hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
FILTERED = Path('/tmp/collections-perf/cli-key-scaling/ux-local-production-v2/warmup/filtered-checks-candidate/stdout.txt').read_bytes()
FLOWS = {
    'core': ['-m', 'core', 'api', 'call', 'version'],
    'expanded': ['check', '-l', '--all'],
    'filtered': ['check', '-l', '--all', 'go/modules/tests/run', '--go-module=.', '--go-test=TestFormatResponse'],
    'execute': ['check', '--generated=false', 'go/modules/tests/run', '--go-module=.', '--go-test=TestFormatResponse'],
    'native-call': ['-m', './module', 'api', 'call', 'read'],
    'native-check': ['check', '--generated=false', 'verify'],
    'native-generate': ['-y', 'generate', 'render'],
    'native-up': ['up', 'web'],
    'export': ['-m', 'core', 'api', 'call', 'host', 'file', '--path', 'input.txt', 'export', '--path', './exported.txt'],
}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def capture(cmd): return subprocess.check_output(cmd,text=True).strip()
def write(path,data): path.write_text(json.dumps(data,indent=2)+'\n')
def inspect(name): return json.loads(capture(['docker','inspect',name]))[0]
def get(port,path):
    with HTTP.open(f'http://127.0.0.1:{port}'+path,timeout=30) as f: return f.read()
def source_hashes(app):
    return {n:sha(app/n) for n in ('main.go','main_test.go','dagger.toml')}

def fixture_hashes(app):
    result={}
    for directory,names,files in os.walk(app):
        names[:]=[n for n in names if n not in ('.git','node_modules')]
        for name in files:
            path=Path(directory)/name
            if path.is_file():result[str(path.relative_to(app))]=sha(path)
    return result

def prepare():
    assert not (LAB/'prepared.json').exists(), 'already prepared'
    build=json.loads((LAB/'builds.json').read_text())
    image=capture(['docker','image','inspect','--format','{{.Id}}','sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'])
    assert image=='sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
    app=LAB/'greetings';shutil.copytree(SDK/'ts-static/greetings',app,symlinks=True)
    native=LAB/'native';native.mkdir()
    shutil.copytree(Path('/tmp/collections-perf/cli-key-scaling/vertical-fixture'),native/'module')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));service_port=sock.getsockname()[1]
    (native/'dagger.toml').write_text(f'[modules.perf-flows]\nsource = "./module"\nentrypoint = true\n\n[ports."{service_port}"]\nbackendService = "web"\nbackendPort = 8080\n')
    (native/'input.txt').write_text('warm\n')
    subprocess.run(['git','init','--quiet'],cwd=native,check=True)
    subprocess.run(['git','add','dagger.toml','input.txt','module'],cwd=native,check=True)
    subprocess.run(['git','-c','user.name=Dagger performance fixture','-c','user.email=perf-fixture@localhost','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','--quiet','-m','Synthetic performance fixture'],cwd=native,check=True)
    (LAB/'empty-config').mkdir(mode=0o700)
    manifest={'source_hashes':source_hashes(app),'fixture_hashes_excluding_git_and_node_modules':fixture_hashes(app),'service_port':service_port,'cli_sha256':sha(CLI),'image':image,'containers':{},'blobs':{},'builds':build,
        'scope':'Fresh matched control and candidates from current source with the same experimental SDK overlays; not a comparison against the older retained engine.',
        'boundary':'Fresh CLI spawn through blocking waitpid; setup, snapshots, pauses and profiles outside ordinary timed intervals.'}
    blobs={p.name:p for folder in ('/tmp/collections-perf/prebuilt-ts-sdk/blobs','/tmp/collections-perf/half-second/node-compile/blobs') for p in Path(folder).iterdir() if p.is_file()}
    manifest['blobs']={str(p):sha(p) for p in blobs.values()}
    for index,variant in enumerate(VARIANTS):
        item=build[variant];binary=Path(item['binary']);assert sha(binary)==item['sha256']
        name='dagger-engine.collections-alloc2-'+variant;port=6284+index
        for kind in ('container','volume'):
            assert subprocess.run(['docker',kind,'inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0, 'resource already exists'
        capture(['docker','volume','create','--label','dagger.perf.owner='+OWNER,name])
        cid=capture(['docker','create','--name',name,'--label','dagger.perf.owner='+OWNER,'--privileged','-p',f'127.0.0.1:{port}:6060','-v',name+':/var/lib/dagger',
            '-e','DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST=sha256:2a8f755cfe5322aeeee861f646c58d6b796a585d2794db47b5b71ba14f6f3fef',
            '-e','_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT=',image,'--debugaddr=0.0.0.0:6060'])
        manifest['containers'][variant]={'name':name,'id':cid,'port':port,'sha256':item['sha256']}
        write(LAB/'prepared.json',manifest)
        capture(['docker','cp',str(binary),name+':/usr/local/bin/dagger-engine'])
        for filename,path in blobs.items(): capture(['docker','cp',str(path),name+':/usr/local/share/dagger/content/blobs/sha256/'+filename])
    write(LAB/'prepared.json',manifest)
    print(json.dumps({'prepared':list(manifest['containers']),'started':False}),flush=True)

def owned(item):
    info=inspect(item['name'])
    assert info['Id']==item['id'] and info['Config']['Labels'].get('dagger.perf.owner')==OWNER
    return info

def start(item):
    begin=time.monotonic()
    info=owned(item)
    if not info['State']['Running']: capture(['docker','start',item['name']])
    for _ in range(300):
        try: get(item['port'],'/debug/pprof/');break
        except OSError: time.sleep(.1)
    else: raise TimeoutError('engine readiness')
    assert capture(['docker','exec',item['name'],'sha256sum','/usr/local/bin/dagger-engine']).split()[0]==item['sha256']
    return time.monotonic()-begin

def stop(manifest):
    for item in manifest['containers'].values():
        if owned(item)['State']['Running']: capture(['docker','stop','--timeout','30',item['name']])
    print(json.dumps({'stopped_owned_engines':len(manifest['containers']),'volumes_deleted':0}),flush=True)

def run_trial(manifest,production=False):
    dest=LAB/('production-v1' if production else 'local-v1');dest.mkdir(mode=0o700,exist_ok=False)
    (dest/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
    assert sha(CLI)==manifest['cli_sha256']
    app=LAB/'greetings';native=LAB/'native';assert source_hashes(app)==manifest['source_hashes']
    original={n:(app/n).read_bytes() for n in manifest['source_hashes']}
    assert fixture_hashes(app)==manifest['fixture_hashes_excluding_git_and_node_modules']
    common={k:os.environ[k] for k in ('PATH','HOME','USER','LOGNAME','TMPDIR') if k in os.environ}
    common.update(DO_NOT_TRACK='1',DAGGER_NO_UPDATE_CHECK='1',GIT_TERMINAL_PROMPT='0')
    if production:
        common['DAGGER_CLOUD_URL']='https://api.dagger.cloud'
        for k in ('DAGGER_CLOUD_TOKEN','XDG_CONFIG_HOME'):
            if os.environ.get(k):common[k]=os.environ[k]
    else: common['XDG_CONFIG_HOME']=str(LAB/'empty-config')
    variants=('base','combined') if production else VARIANTS
    if production:
        for variant in variants: start(manifest['containers'][variant])
    rows=[]
    core_expected=None
    startup={}
    native_outputs={n:(native/n).read_bytes() if (native/n).exists() else None for n in ('generated.txt','exported.txt')}
    write(dest/'provenance.json',{'manifest':manifest,'flows':FLOWS,'production':production,'production_commands_max':16 if production else 0,'driver_sha256':sha(__file__),
        'ordinary_timings':'No CPU/wcprof profiler, forced GC or polling waitpid in timed loops. Numeric MemStats/pressure snapshots outside CLI time.',
        'environment':'Normal Cloud login and explicit production endpoint' if production else 'Empty auth config, no Cloud or OTLP exporters',
        'cold':'Only first expanded call per new engine volume; host pages/images may be warm. One sample per variant is diagnostic, not an estimate.'})

    def snapshot(item):
        assert shutil.disk_usage(LAB).free>16*1024**3,'benchmark free-space floor reached'
        mem=json.loads(get(item['port'],'/debug/vars'))['memstats']
        psi={k:{l.split()[0]:int(l.rsplit('=',1)[1]) for l in Path('/proc/pressure',k).read_text().splitlines()} for k in ('cpu','io','memory')}
        info=owned(item);pid=info['State']['Pid']
        group=Path('/sys/fs/cgroup')/Path('/proc',str(pid),'cgroup').read_text().split('::')[1].strip().lstrip('/')
        if group.name=='init':group=group.parent
        io={l.split()[0]:{k:int(v) for k,v in (kv.split('=') for kv in l.split()[1:])} for l in (group/'io.stat').read_text().splitlines()}
        cpu={l.split()[0]:int(l.split()[1]) for l in (group/'cpu.stat').read_text().splitlines()}
        return {'memstats':{k:mem[k] for k in ('TotalAlloc','Mallocs','NumGC','NumForcedGC','PauseTotalNs','HeapAlloc')},'host_psi_us':psi,'engine_io':io,'engine_cpu':cpu,'free_disk_bytes':shutil.disk_usage(LAB).free}

    def run(variant,flow,phase,index,expected=None,profile=False,fail=False):
        nonlocal core_expected
        item=manifest['containers'][variant];out=dest/f'{phase}-{index}-{flow}-{variant}';out.mkdir()
        cwd=native if flow.startswith('native-') or flow=='export' else app
        if flow=='export':(native/'exported.txt').unlink(missing_ok=True)
        if flow=='native-generate':(native/'generated.txt').unlink(missing_ok=True)
        if flow=='native-up':
            with socket.socket() as sock:assert sock.connect_ex(('127.0.0.1',manifest['service_port']))!=0,'service port already listening'
        if profile:
            try:(out/'prior.wcprof').write_bytes(get(item['port'],'/debug/wcprof/dump?flush=true'))
            except HTTPError as e:
                if e.code!=503:raise
        before=snapshot(item)
        done=threading.Event();obs={};ready=None;visible=None;cancelled=None
        command=[str(CLI),'--engine','container://'+item['name']]+(['--profile'] if profile else [])+FLOWS[flow]
        with (out/'stdout.txt').open('wb') as stdout,(out/'stderr.txt').open('wb') as stderr:
            wall=time.time_ns();begin=time.monotonic()
            proc=subprocess.Popen(command,cwd=cwd,env=common,stdout=stdout,stderr=stderr,start_new_session=True)
            def waiter():
                obs['status']=proc.wait();obs['time']=time.monotonic();obs['wall']=time.time_ns();done.set()
            waiter_thread=threading.Thread(target=waiter,daemon=True);waiter_thread.start()
            try:
                if flow=='native-up':
                    while time.monotonic()-begin<120:
                        if done.is_set():raise RuntimeError('service exited before ready: '+out.name)
                        try:
                            with HTTP.open(f'http://127.0.0.1:{manifest["service_port"]}/',timeout=.1) as response:
                                if response.read()==(native/'input.txt').read_bytes():ready=time.monotonic();break
                        except (URLError,TimeoutError,ConnectionError):pass
                        time.sleep(.005)
                    if ready is None:raise TimeoutError('service readiness: '+out.name)
                    cancelled=time.monotonic();proc.send_signal(signal.SIGINT)
                if flow in ('native-generate','export'):
                    output=native/('generated.txt' if flow=='native-generate' else 'exported.txt')
                    while time.monotonic()-begin<120:
                        try:
                            if output.read_bytes()==(native/'input.txt').read_bytes():visible=time.monotonic();break
                        except FileNotFoundError:pass
                        if done.is_set():break
                        time.sleep(.005)
                if not done.wait(240 if phase=='first' else 120):raise TimeoutError(str(out))
            finally:
                if not done.is_set():
                    proc.send_signal(signal.SIGINT)
                    if not done.wait(10):os.killpg(proc.pid,signal.SIGKILL)
                waiter_thread.join(timeout=15)
                assert not waiter_thread.is_alive(),'owned CLI did not exit'
        after=snapshot(item);stdout=(out/'stdout.txt').read_bytes();stderr=(out/'stderr.txt').read_bytes()
        text=re.sub(rb'\x1b\[[0-9;]*m',b'',stdout+b'\n'+stderr)
        if fail:
            assert obs['status']!=0 and b'perf-flows correctness sentinel' in text,('failure sentinel not observed',out.name)
        else:assert obs['status'] in ({0,2} if flow=='native-up' and ready is not None else {0}), ('command failed; inspect private output',out.name)
        if fail:pass
        elif flow=='expanded':
            want=WANT if expected is None else expected
            normalize=lambda b:sorted(tuple(p.strip() for p in l.split(b'#',1)) for l in b.splitlines() if l.strip())
            assert normalize(stdout)==normalize(want),('expanded output mismatch',out.name)
        elif flow=='filtered': assert stdout==FILTERED,('filtered output mismatch',out.name)
        elif flow in ('execute','native-check'):
            assert re.search(rb'\b1 passed\b',text),('check did not pass',out.name)
            if flow=='execute':assert b'dag://go/modules/tests/run?go-module=.&go-test=TestFormatResponse' in text,('wrong check identity',out.name)
        elif flow=='native-call': assert stdout==(native/'input.txt').read_bytes()
        elif flow=='export': assert (native/'exported.txt').read_bytes()==(native/'input.txt').read_bytes()
        elif flow=='native-generate': assert (native/'generated.txt').read_bytes()==(native/'input.txt').read_bytes()
        elif flow=='native-up':
            deadline=time.monotonic()+3
            while True:
                try:
                    with socket.create_connection(('127.0.0.1',manifest['service_port']),timeout=.1):pass
                except OSError:break
                if time.monotonic()>deadline:raise RuntimeError('service tunnel not released')
                time.sleep(.02)
        elif flow=='core':
            assert stdout.strip(), 'empty core result'
            if core_expected is None:core_expected=stdout
            else:assert stdout==core_expected,'engine version result differs between matched variants'
        if production and phase=='auth':assert re.search(rb'https://dagger\.cloud/[^/\s]+/traces/[0-9a-f]{32}',text),'normal production login not confirmed'
        row={'variant':variant,'flow':flow,'phase':phase,'index':index,'profile':profile,'seconds':obs['time']-begin,'started_unix_ns':wall,'exited_unix_ns':obs['wall'],'exit_code':obs['status'],'stdout_sha256':sha(out/'stdout.txt'),'stderr_bytes':len(stderr),'before':before,'after':after,'correct':True}
        row['engine_allocated_bytes']=after['memstats']['TotalAlloc']-before['memstats']['TotalAlloc']
        row['engine_gc_cycles']=after['memstats']['NumGC']-before['memstats']['NumGC']
        row['expected_failure']=fail
        row['engine_written_bytes']=sum(v.get('wbytes',0)-before['engine_io'].get(k,{}).get('wbytes',0) for k,v in after['engine_io'].items())
        assert row['engine_written_bytes']<32*1024**3,'owned engine exceeded per-command write bound'
        if ready is not None:row.update(http_ready_seconds=ready-begin,cancel_to_exit_seconds=obs['time']-cancelled)
        if flow in ('native-generate','export'):row.update(file_visible_seconds=visible-begin if visible else None,file_visibility_poll_ms=5)
        rows.append(row);write(dest/'results.json',rows)
        print(json.dumps({k:row[k] for k in ('variant','flow','phase','index','seconds','engine_allocated_bytes','engine_gc_cycles','correct')}),flush=True)
        if profile:(out/'run.wcprof').write_bytes(get(item['port'],'/debug/wcprof/dump?flush=true'))
        time.sleep(1 if production else .3)

    try:
        if production:
            for variant in variants:run(variant,'core','auth',0)
            for variant in variants:run(variant,'expanded','warmup',0)
            for index in range(3):
                for flow in ('expanded','execute'):
                    for variant in (variants if index%2==0 else tuple(reversed(variants))):run(variant,flow,'warm',index)
        else:
            for variant in variants:
                startup[variant]=start(manifest['containers'][variant]);write(dest/'startup.json',startup)
                run(variant,'expanded','first',0)
                for flow in FLOWS:run(variant,flow,'warmup',0)
            for index in range(6):
                order=variants[index%3:]+variants[:index%3]
                if index%2:order=tuple(reversed(order))
                for flow in FLOWS:
                    for variant in order:run(variant,flow,'warm',index)
            for index in range(3):
                order=variants[index:]+variants[:index]
                marker=f'TestFormatResponseAllocProbe{index}'.encode()
                assert original['main_test.go'].count(b'TestFormatResponse(')==1
                (app/'main_test.go').write_bytes(original['main_test.go'].replace(b'TestFormatResponse(',marker+b'('))
                expected=WANT.replace(b'TestFormatResponse ',marker+b' ')
                assert expected!=WANT
                for variant in order:run(variant,'expanded','rename',index,expected)
                (app/'main_test.go').write_bytes(original['main_test.go'])
                (app/'main.go').write_bytes(original['main.go']+f'\n// user edit allocation probe {index}\n'.encode())
                for variant in tuple(reversed(order)):run(variant,'expanded','user-comment',index)
                (app/'main.go').write_bytes(original['main.go']+f'\n// direct check edit allocation probe {index}\n'.encode())
                for variant in order:run(variant,'execute','direct-check-edit',index)
                (app/'main.go').write_bytes(original['main.go'])
                (native/'input.txt').write_text(f'edit {index}\n')
                for flow in ('native-call','native-check','native-generate','native-up','export'):
                    for variant in order:run(variant,flow,'input-edit',index)
            (native/'input.txt').write_text('fail\n')
            for variant in variants:run(variant,'native-check','correctness-failure',0,fail=True)
            (native/'input.txt').write_text('restored\n')
            for variant in variants:run(variant,'native-check','correctness-recovery',0)
            for variant in variants:
                for flow in ('core','expanded','filtered'):run(variant,flow,'profile',0,profile=True)
    finally:
        for n,b in original.items():(app/n).write_bytes(b)
        (native/'input.txt').write_text('warm\n')
        for n,b in native_outputs.items():
            if b is None:(native/n).unlink(missing_ok=True)
            else:(native/n).write_bytes(b)
        assert source_hashes(app)==manifest['source_hashes']
        after_fixture=fixture_hashes(app)
        original_fixture=manifest['fixture_hashes_excluding_git_and_node_modules']
        changed=[p for p,digest in original_fixture.items() if after_fixture.get(p)!=digest]
        assert not changed,('existing fixture files changed',changed)
        write(dest/'restoration.json',{'source_restored':True,'source_hashes':source_hashes(app),'existing_fixture_files_preserved':True,'created_fixture_files':sorted(set(after_fixture)-set(original_fixture))})
    summary=[]
    for phase,flow in sorted({(r['phase'],r['flow']) for r in rows if not r['profile']}):
        item={'phase':phase,'flow':flow}
        for variant in variants:
            selected=[r for r in rows if r['variant']==variant and r['flow']==flow and r['phase']==phase]
            item[variant]={'n':len(selected),'seconds':[r['seconds'] for r in selected],'median_seconds':statistics.median(r['seconds'] for r in selected),'median_allocated_bytes':statistics.median(r['engine_allocated_bytes'] for r in selected)}
            if flow=='native-up':item[variant].update(http_ready_seconds=[r['http_ready_seconds'] for r in selected],median_http_ready_seconds=statistics.median(r['http_ready_seconds'] for r in selected))
        summary.append(item)
    write(dest/'summary.json',summary)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','local','production','stop'));parser.add_argument('--run',action='store_true');args=parser.parse_args()
    if not args.run:print(json.dumps({'action':args.action,'variants':VARIANTS,'flows':FLOWS,'execute':False}));raise SystemExit()
    os.umask(0o077)
    if args.action=='prepare':prepare()
    else:
        manifest=json.loads((LAB/'prepared.json').read_text())
        if args.action=='stop':stop(manifest)
        else:run_trial(manifest,production=args.action=='production')
