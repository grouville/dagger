from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import argparse,json,os,re,secrets,statistics,subprocess,time,urllib.parse,urllib.request
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--pairs',type=int,default=8)
parser.add_argument('--files',type=int,default=10000)
parser.add_argument('--profile',action='store_true')
parser.add_argument('--lazy-account',action='store_true')
parser.add_argument('--output-root',type=Path,required=True)
args=parser.parse_args()
root=args.output_root;root.mkdir(exist_ok=False)
base=Path('/tmp/rust-cache-sipsma-review');debug='http://127.0.0.1:16104/debug/'
source=Path('/tmp/rust-native-config-entry-1026-before');config=source/'dagger.toml';original=config.read_text()
cli=str(base/'dagger-artifact-list-buffered')
removed={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
record=json.loads(subprocess.check_output(['docker','inspect','dagger-rust-parser-state-pool-oct14']))[0]
engine=Path('/sys/fs/cgroup')/Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':',2)[2].strip().lstrip('/')
groups={'engine':engine,'docker_total':engine.parent,'exec':engine.parent/'exec'}

def get(route,data=None,timeout=180):
    with urllib.request.urlopen(urllib.request.Request(debug+route,data=data),timeout=timeout) as response:return json.load(response)
def action(name,**kwargs):return get('snapshot-collection?'+urllib.parse.urlencode(dict(action=name,**{k:str(v).lower() if isinstance(v,bool) else v for k,v in kwargs.items()})),b'')
def status(snapshot=''):return get('snapshot-collection?'+urllib.parse.urlencode({'snapshot':snapshot}))
def mode(name,value):assert get(name+'?enabled='+str(value).lower(),b'')['enabled']==value
def source_mode(value):subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n' if value else b'off\n',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
def cpu():return {name:next(int(s.split()[1]) for s in (path/'cpu.stat').read_text().splitlines() if s.startswith('usage_usec '))/1e6 for name,path in groups.items()}
def pressure():
    values={}
    for prefix,path in [('host',Path('/proc/pressure')),('engine',engine)]:
        for kind in ['cpu','io','memory']:
            for line in (path/(kind if prefix=='host' else kind+'.pressure')).read_text().splitlines():values[prefix+'.'+kind+'.'+line.split()[0]]=int(line.split('total=')[1])
    return values

def idle(label,quiet=True):
    started=time.monotonic()
    while True:
        before=pressure();t=time.monotonic();time.sleep(1 if quiet else .1);after=pressure();elapsed=time.monotonic()-t
        state=get('client-lifecycle');fractions={k:(after[k]-before[k])/(elapsed*1e6) for k in before}
        inactive=not state.get('sessions') and state['active_requests']==0
        admitted=inactive and (not quiet or (fractions['host.io.some']<.05 and fractions['engine.io.some']<.01))
        with (root/'admission.jsonl').open('a') as out:out.write(json.dumps(dict(label=label,seconds=time.monotonic()-started,quiet=quiet,admitted=admitted,stall_fraction=fractions))+'\n')
        if admitted:return
        assert time.monotonic()-started<90,'idle admission timeout; retain prior samples'

def unix(value):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def dump(label):
    with urllib.request.urlopen(debug+'wcprof/dump',timeout=20) as response,(root/(label+'.ndjson')).open('wb') as output:
        while data:=response.read(1048576):output.write(data)
    with (root/(label+'.ndjson')).open() as stream:
        header=json.loads(next(stream))
    assert not header['dropped_events'] and not header.get('open_ops'),label

def background(scenario):
    begin=time.time()
    result=get('cache-usage-measurement?enabled=true',b'') if scenario=='account-lazy' else action(scenario)
    result['request_started_unix']=begin;result['request_finished_unix']=time.time()
    return result

rows=[]
orders=[['idle','account','collect'],['collect','account','idle'],['account','idle','collect'],['idle','collect','account'],['collect','idle','account'],['account','collect','idle']]
if args.lazy_account:
    orders=[['idle','account','account-lazy','collect'],['collect','account-lazy','account','idle'],['account','idle','collect','account-lazy'],['account-lazy','collect','idle','account'],['idle','account-lazy','collect','account'],['account','collect','account-lazy','idle'],['collect','account','idle','account-lazy'],['account-lazy','idle','account','collect']]
try:
    config.write_text(re.sub(r'source = "[^"]+"','source = "/tmp/dagger-rust-native-deep-artifact-closures"',original,count=1))
    assert not get('wcprof/enabled')['global_enabled'];assert get('scalar-array-restore')['enabled']
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    mode('direct-span-protobuf',False);mode('snapshot-completions',False);source_mode(True)
    idle('initial')
    action('mode',deferred=True,drain=True)
    metadata=dict(files=args.files,pairs=args.pairs,profile=args.profile,lazy_account=args.lazy_account,engine_id=record['Id'],engine_started=record['State']['StartedAt'],module='f73c5614a89968afa6f6000328e96ea33745fd93',same_history=True,command='check rust:packages/check',engine_counter_scope='engine and sibling exec recorded separately; docker_total overlaps both',cpu_paths={k:str(v) for k,v in groups.items()},telemetry_enabled=True,native_source_seeds=True,compact_scalar_restore=True,dagql_pruning_not_disabled=True,natural_containerd_collections_deferred=True,forced_jobs='readonly account or containerd collect only; no explicit cache-root eviction',deferred_collection_drained_after_each_command=True,post_admission_stalls_excluded=False,initial_state=status())
    (root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    with ThreadPoolExecutor(max_workers=1) as pool:
        for pair in range(-1,args.pairs):
            for scenario in orders[pair%len(orders)]:
                label=f'{pair}-{scenario}'
                idle(label+'-before-preparation')
                action('collect')
                prepared=action('prepare',files=args.files);snapshot=prepared['snapshot_id']
                assert status(snapshot)['snapshot_exists'],(label,'scratch snapshot was not retained until collection')
                path=source/'leaf_1023/src/lib.rs';text,count=re.subn(r'pub const EDIT: u64 = \d+;',f'pub const EDIT: u64 = {secrets.randbits(48)};',path.read_text());assert count==1;path.write_text(text)
                idle(label)
                if args.profile:
                    get('wcprof/enabled',b'on')
                    with urllib.request.urlopen(debug+'wcprof/dump',timeout=20) as response:
                        while response.read(1048576):pass
                before_cpu=cpu();before_pressure=pressure();case_start=time.monotonic();case_unix=time.time()
                future=pool.submit(background,scenario) if scenario!='idle' else pool.submit(lambda:None)
                command_start=time.monotonic();command_unix=time.time()
                with (root/(label+'.log')).open('w') as output:process=subprocess.run([cli,'check','rust:packages/check'],cwd=source,env=env,stdout=output,stderr=subprocess.STDOUT)
                command_seconds=time.monotonic()-command_start;command_end_unix=time.time()
                cpu_at_command=cpu();after_pressure=pressure()
                job=future.result()
                job_finished=time.monotonic()
                assert process.returncode==0 and 'passed' in (root/(label+'.log')).read_text(),label
                if args.profile:
                    get('wcprof/enabled',b'off');dump(label)
                state_after_command=status(snapshot)
                if scenario=='collect':assert not state_after_command['snapshot_exists'],(label,'forced collector did not reclaim scratch')
                else:assert state_after_command['snapshot_exists'],(label,'ordinary collection escaped deferral')
                idle(label+'-teardown',quiet=False)
                drain_started=time.monotonic();drain=action('collect');drain_seconds=time.monotonic()-drain_started
                state_after=status(snapshot);assert not state_after['snapshot_exists'],(label,'scratch was not reclaimed after drain')
                assert state_after['deferred']
                total_seconds=time.monotonic()-case_start;after_cpu=cpu()
                overlap=None
                if job and 'started_at' in job:
                    overlap=max(0.,min(command_end_unix,unix(job['ended_at']))-max(command_unix,unix(job['started_at'])))
                row=dict(pair=pair,scenario=scenario,label=label,preparation=pair<0,scratch=prepared,command_seconds=command_seconds,case_seconds=total_seconds,command_unix_start=command_unix,case_unix_start=case_unix,job=job,job_command_overlap_seconds=overlap,future_observation_wait_seconds=max(0.,job_finished-command_start-command_seconds),drain_seconds=drain_seconds,drain=drain,command_cpu_seconds={k:cpu_at_command[k]-before_cpu[k] for k in groups},whole_case_cpu_seconds={k:after_cpu[k]-before_cpu[k] for k in groups},stall_fraction={k:(after_pressure[k]-before_pressure[k])/(command_seconds*1e6) for k in before_pressure},after_command=state_after_command,after_drain=state_after)
                rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
                print(label,'command',round(command_seconds,3),'job',None if job is None else round(job['seconds'],3),'drain',round(drain_seconds,3),'whole case',round(total_seconds,3),'overlap',overlap,flush=True)
    measured=[r for r in rows if not r['preparation']]
    summary={scenario:{key:statistics.median(r[key] for r in measured if r['scenario']==scenario) for key in ['command_seconds','case_seconds','drain_seconds']} for scenario in orders[0]}
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
finally:
    config.write_text(original)
    get('wcprof/enabled',b'off')
    action('mode',deferred=False,drain=True)
    source_mode(False);mode('batch-metadata',False);mode('attribute-array-decode',False)
