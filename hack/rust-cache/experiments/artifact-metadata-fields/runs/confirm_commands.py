from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import secrets
import statistics
import itertools
import random
import subprocess
import time
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--output-root', type=Path, required=True)
parser.add_argument('--pairs', type=int, default=8)
parser.add_argument('--profile', action='store_true')
parser.add_argument('--force-go-gc', action='store_true')
parser.add_argument('--kinds', nargs='+', choices=['large','direct','tests','list'], default=['large','direct','tests','list'])
args = parser.parse_args()
root = args.output_root
root.mkdir(exist_ok=False)
base = Path('/tmp/rust-cache-sipsma-review')
source = Path('/tmp/rust-native-config-entry-1026-before')
config = source / 'dagger.toml'
original_config = config.read_text()
debug = 'http://127.0.0.1:16104/debug/'
cli = base / 'dagger-artifact-list-buffered'
module = Path('/tmp/dagger-rust-native-deep-artifact-closures')
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
engine = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
groups = {'engine': engine, 'exec': engine.parent / 'exec', 'docker_total': engine.parent}
removed = {'DAGGER_SESSION_PORT', 'DAGGER_SESSION_TOKEN', 'SSH_AUTH_SOCK', 'DAGGER_CLOUD_TOKEN', 'DAGGER_CLOUD_URL', 'DAGGER_ENGINE', 'DAGGER_CLOUD_ENGINE', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'}
env = {k: v for k, v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://' + (base / 'otlp-null-address.txt').read_text().strip() + ':43184', DAGGER_CLOUD_TOKEN='local-benchmark-token', XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config', NO_PROXY='*', _EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')


def get(route, data=None, timeout=180):
    with urllib.request.urlopen(urllib.request.Request(debug + route, data=data), timeout=timeout) as response:
        return json.load(response)


def action(name, **options):
    return get('snapshot-collection?' + urllib.parse.urlencode(dict(action=name, **{k: str(v).lower() if isinstance(v, bool) else v for k, v in options.items()})), b'')


def mode(route, enabled):
    assert get(route + '?enabled=' + str(enabled).lower(), b'')['enabled'] == enabled


def source_mode(enabled):
    subprocess.run(['docker', 'exec', '-i', record['Id'], 'sh', '-c', 'cat > /tmp/filesync-snapshot-seeds-mode'], input=b'on\n' if enabled else b'off\n', check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def pressure():
    values = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', engine)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                values[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return values


def cpu():
    return {k: next(int(line.split()[1]) for line in (p / 'cpu.stat').read_text().splitlines() if line.startswith('usage_usec ')) / 1e6 for k, p in groups.items()}


def heap():
    value = get('vars')['memstats']
    return {k: value[k] for k in ['HeapAlloc', 'HeapInuse', 'HeapIdle', 'HeapReleased', 'HeapObjects', 'TotalAlloc', 'Mallocs', 'Frees', 'NumGC', 'NextGC', 'PauseTotalNs', 'GCCPUFraction']}


def idle(label, quiet=True):
    started = time.monotonic()
    while True:
        before = pressure()
        engine_cpu_before = cpu()['engine']
        mark = time.monotonic()
        time.sleep(1 if quiet else .1)
        after = pressure()
        elapsed = time.monotonic() - mark
        state = get('client-lifecycle')
        stalls = {k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}
        engine_cpu_rate = (cpu()['engine'] - engine_cpu_before) / elapsed
        admitted = not state.get('sessions') and state['active_requests'] == 0 and (not quiet or (stalls['host.io.some'] < .05 and stalls['engine.io.some'] < .01 and stalls['host.cpu.some'] < .10 and engine_cpu_rate < .10))
        with (root / 'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label, admitted=admitted, stall_fraction=stalls, engine_cpu_rate=engine_cpu_rate, seconds=time.monotonic() - started)) + '\n')
        if admitted:
            return
        assert time.monotonic() - started < 90, 'admission timeout; preserve all completed observations'


def unix(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def nondeferred_overlaps(state, started, ended):
    return [event for event in state['events'] if not event['deferred'] and unix(event['start']) < ended and unix(event['end']) > started]


def profile_start():
    get('wcprof/enabled', b'on')
    with urllib.request.urlopen(debug + 'wcprof/dump', timeout=20) as response:
        while response.read(1048576):
            pass


def profile_end(label):
    get('wcprof/enabled', b'off')
    with urllib.request.urlopen(debug + 'wcprof/dump', timeout=20) as response:
        (root / (label + '.ndjson')).write_bytes(response.read())
    with (root / (label + '.ndjson')).open() as stream:
        header = json.loads(next(stream))
    assert not header['dropped_events'] and not header.get('open_ops'), label


modules={'before':Path('/tmp/dagger-rust-native-discovery-current'),'after':Path('/tmp/dagger-rust-native-discovery-current')}
workloads={
 'list':dict(size='1026',file='leaf_1023/src/lib.rs',selection='rust:packages/check',cargo='metadata'),
 'large':dict(size='1026',file='leaf_1023/src/lib.rs',selection='rust:packages/check',cargo='check'),
 'direct':dict(size='130',file='leaf_0127/src/lib.rs',selection='rust:check',cargo='check'),
 'tests':dict(size='small',file='app/src/lib.rs',selection='rust:packages/test',cargo='test'),
}
workloads={k:workloads[k] for k in args.kinds}
originals={}
toolchain=Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
for data in workloads.values():
 data['source']=Path('/tmp/rust-native-config-entry-'+data['size']+'-before')
 path=data['source']/'dagger.toml';originals[path]=path.read_text()
orders=[['before','after','cargo'],['cargo','after','before'],['after','cargo','before'],['before','cargo','after'],['cargo','before','after'],['after','before','cargo']]
random_seed=2026101609
rng=random.Random(random_seed)
all_orders=list(itertools.permutations(['before','after','cargo']))
orders_by_kind={}
for kind in workloads:
 before_first=[list(o) for o in all_orders if o.index('before')<o.index('after')]
 after_first=[list(o) for o in all_orders if o.index('after')<o.index('before')]
 selected=[rng.choice(before_first) for _ in range((args.pairs+1)//2)]+[rng.choice(after_first) for _ in range(args.pairs//2)]
 rng.shuffle(selected);orders_by_kind[kind]=selected
rows=[]
try:
 assert not args.force_go_gc
 assert not get('wcprof/enabled')['global_enabled']
 assert not get('snapshot-collection')['deferred']
 assert get('dimension-key-fields')['enabled']
 assert not get('parallel-fingerprint')['enabled']
 mode('batch-metadata',True);mode('attribute-array-decode',True)
 mode('direct-span-protobuf',False);mode('snapshot-completions',False);mode('containerd-root-dedup',False);source_mode(True)
 meta=dict(engine=json.loads((base/'artifact-metadata-fields/identity.json').read_text()),
           modules={k:dict(path=str(path),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip()) for k,path in modules.items()},
           pairs=args.pairs,kinds=args.kinds,profile=args.profile,orders=orders,orders_by_kind=orders_by_kind,random_seed=random_seed,dimension_key_fields_direct=True,spill_batch_buffers=False,compiler_tree='0c9e8b107593d1e5a623145c7b004258c192d060',same_physical_source_and_history=True,
           compiler_and_engine_warm=True,fresh_processes=True,telemetry_enabled=True,source_snapshot_seeds=True,
           natural_collection=True,no_scratch_snapshots=True,no_forced_collection=True,no_forced_Go_collection=True,
           initial_heap=heap(),scope='Original versus direct artifact description and URI strings; cached object lists preserved; selected native-discovery module; balanced randomized order, all admitted observations retained.')
 (root/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
 for pair in range(-1,args.pairs):
  for kind,data in workloads.items():
   for arm in (orders[-1] if pair<0 else orders_by_kind[kind][pair]):
    label=str(pair)+'-'+kind+'-'+arm
    path=data['source']/'dagger.toml'
    if arm!='cargo':
     text,count=re.subn(r'source = "[^"]+"','source = "'+str(modules[arm])+'"',originals[path],count=1);assert count==1;path.write_text(text)
    filename=data['source']/data['file']
    edit_value=secrets.randbits(48)
    if kind=='tests':pattern=r'pub fn edited_value\(\) -> u64 \{ \d+ \}';replacement='pub fn edited_value() -> u64 { '+str(edit_value)+' }'
    else:pattern=r'pub const EDIT: u64 = \d+;';replacement='pub const EDIT: u64 = '+str(edit_value)+';'
    text,count=re.subn(pattern,replacement,filename.read_text());assert count==1;filename.write_text(text)
    idle(label)
    mode('artifact-metadata-fields',arm=='after')
    run_env=dict(env)
    if arm=='cargo':
     run_env.update(RUSTC=str(toolchain/'rustc'),RUSTDOC=str(toolchain/'rustdoc'),CARGO_INCREMENTAL='1',CARGO_BUILD_JOBS='8',CARGO_TARGET_DIR=str(base/('native-config-entry-'+data['size']+'-cargo-target')))
     for name in ['RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_BUILD_BUILD_DIR']:run_env.pop(name,None)
     command=[str(toolchain/'cargo'),data['cargo'],'--workspace','--locked','--offline']
     if kind=='list':command=[str(toolchain/'cargo'),'metadata','--no-deps','--format-version=1','--locked','--offline']
    else:
     command=[str(cli),'check',data['selection']]
     if kind=='list':command=[str(cli),'check','--list','--all',data['selection']]
    if args.profile:profile_start()
    before_heap=heap();before_cpu=cpu();before_pressure=pressure()
    unix_start=time.time();started=time.monotonic()
    with (root/(label+'.log')).open('w') as output:
     result=subprocess.run(command,cwd=data['source'],env=run_env,stdout=output,stderr=subprocess.STDOUT)
    seconds=time.monotonic()-started;unix_end=time.time()
    after_cpu=cpu();after_pressure=pressure();after_heap=heap()
    assert result.returncode==0,(label,result.returncode)
    log=(root/(label+'.log')).read_text()
    if kind=='list':
     expected={'app','shared'}|{f'leaf_{i:04d}' for i in range(1024)}
     if arm=='cargo':listed=[p['name'] for p in json.loads(log)['packages']]
     else:listed=re.findall(r'^rust\s+(\S+)\s+check$',log,re.M)
     assert len(listed)==1026 and set(listed)==expected,(label,'incomplete package listing',len(listed))
    elif arm!='cargo':assert 'passed' in log,label
    elif kind!='tests' and pair>=0:assert len(set(re.findall(r'Checking ([\w-]+) v',log)))==2,(label,'expected two Cargo compiler actions')
    if args.profile:profile_end(label)
    state=get('snapshot-collection')
    row=dict(pair=pair,kind=kind,arm=arm,label=label,warmup=pair<0,command_seconds=seconds,source_edit_file=data['file'],source_edit_value=edit_value,
             command_unix_start=unix_start,command_unix_end=unix_end,
             before_heap=before_heap,after_heap=after_heap,heap_delta={k:after_heap[k]-before_heap[k] for k in before_heap},
             cpu_seconds={k:after_cpu[k]-before_cpu[k] for k in groups},
             completed_collection_overlaps=nondeferred_overlaps(state,unix_start,unix_end),
             stall_fraction={k:(after_pressure[k]-before_pressure[k])/(seconds*1e6) for k in before_pressure})
    rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,'seconds',round(seconds,4),'engine CPU',round(row['cpu_seconds']['engine'],4),'Go GC',row['heap_delta']['NumGC'],flush=True)
 measured=[r for r in rows if not r['warmup']]
 summary={}
 for kind in workloads:
  data=[r for r in measured if r['kind']==kind]
  byarm={arm:[r for r in data if r['arm']==arm] for arm in ['before','after','cargo']}
  savings=[a['command_seconds']-b['command_seconds'] for a,b in zip(byarm['before'],byarm['after'])]
  summary[kind]=dict(median_seconds={arm:statistics.median(r['command_seconds'] for r in values) for arm,values in byarm.items()},
                    median_paired_saving_seconds=statistics.median(savings),faster_pairs=sum(v>0 for v in savings),pairs=args.pairs,
                    median_engine_cpu={arm:statistics.median(r['cpu_seconds']['engine'] for r in values) for arm,values in byarm.items()},
                    median_engine_allocated_bytes={arm:statistics.median(r['heap_delta']['TotalAlloc'] for r in values) for arm,values in byarm.items()},
                    commands_with_Go_GC={arm:sum(r['heap_delta']['NumGC']>0 for r in values) for arm,values in byarm.items()},
                    max_stall_fraction={k:max(r['stall_fraction'][k] for r in data) for k in data[0]['stall_fraction']})
 (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
finally:
 for path,text in originals.items():path.write_text(text)
 get('wcprof/enabled',b'off');source_mode(False)
 mode('batch-metadata',False);mode('attribute-array-decode',False);mode('containerd-root-dedup',False);mode('artifact-metadata-fields',False)
