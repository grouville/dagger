from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import secrets
import statistics
import subprocess
import time
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--output-root', type=Path, required=True)
parser.add_argument('--pairs', type=int, default=8)
parser.add_argument('--profile', action='store_true')
parser.add_argument('--force-go-gc', action='store_true')
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


assert not args.profile and not args.force_go_gc, "natural cohort keeps profiling and forced Go collection off"
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
cargo_env = dict(env, RUSTC=str(toolchain/'rustc'), RUSTDOC=str(toolchain/'rustdoc'), CARGO_INCREMENTAL='1', CARGO_BUILD_JOBS='8', CARGO_TARGET_DIR=str(base/'native-config-entry-1026-cargo-target'))
orders = [['off','on','cargo'], ['on','cargo','off'], ['cargo','off','on'], ['cargo','on','off'], ['off','cargo','on'], ['on','off','cargo']]
rows = []
try:
    config.write_text(re.sub(r'source = "[^"]+"', 'source = "' + str(module) + '"', original_config, count=1))
    assert not get('wcprof/enabled')['global_enabled']
    assert get('scalar-array-restore')['enabled']
    assert not get('snapshot-collection')['deferred']
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    mode('direct-span-protobuf', False)
    mode('snapshot-completions', False)
    source_mode(True)
    idle('initial')
    (root/'metadata.json').write_text(json.dumps(dict(
        experiment='Edited module check with natural containerd collection; original versus single-lookup root dedup; native Cargo control.',
        pairs=args.pairs, engine_id=record['Id'], engine_started=record['State']['StartedAt'],
        module_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=module,text=True).strip(),
        engine_identity=json.loads((base/'containerd-root-dedup-single-lookup-engine/identity.json').read_text()),
        dagger_command='check rust:packages/check',cargo_command='cargo check --workspace --locked --offline',
        rustc_version=subprocess.check_output([str(toolchain/'rustc'),'--version'],text=True).strip(),
        cargo_target=cargo_env['CARGO_TARGET_DIR'],native_cargo_incremental=True,workers=8,
        same_physical_source=True,fresh_processes=True,warm_engine_and_compiler=True,
        telemetry_enabled=True,profiling=False,natural_collection=True,
        no_forced_collection_between_cases=True,no_scratch_snapshot=True,no_forced_Go_collection=True,
        post_admission_observations_excluded=False,orders=orders,
        cgroup_scope='docker_total overlaps engine and sibling exec; never add all three',
        initial_heap=heap()),indent=2)+'\n')
    for pair in range(-1,args.pairs):
        for arm in orders[pair%len(orders)]:
            label=str(pair)+'-'+arm
            selected_at=time.time()
            if arm!='cargo':mode('containerd-root-dedup',arm=='on')
            path=source/'leaf_1023/src/lib.rs'
            text,count=re.subn(r'pub const EDIT: u64 = \d+;', 'pub const EDIT: u64 = '+str(secrets.randbits(48))+';',path.read_text())
            assert count==1
            path.write_text(text)
            idle(label)
            before_heap=heap();before_cpu=cpu();before_pressure=pressure()
            command=[str(toolchain/'cargo'),'check','--workspace','--locked','--offline'] if arm=='cargo' else [str(cli),'check','rust:packages/check']
            command_unix=time.time();started=time.monotonic()
            with (root/(label+'.log')).open('w') as output:
                result=subprocess.run(command,cwd=source,env=cargo_env if arm=='cargo' else env,stdout=output,stderr=subprocess.STDOUT)
            seconds=time.monotonic()-started;ended_unix=time.time()
            after_cpu=cpu();after_pressure=pressure();after_heap=heap()
            assert result.returncode==0,(label,result.returncode)
            if arm!='cargo':assert 'passed' in (root/(label+'.log')).read_text(),label
            state=get('snapshot-collection')
            assert not state['deferred']
            row=dict(pair=pair,arm=arm,label=label,warmup=pair<0,selected_at=selected_at,
                     command_unix_start=command_unix,command_unix_end=ended_unix,command_seconds=seconds,
                     before_heap=before_heap,after_heap=after_heap,
                     heap_delta={k:after_heap[k]-before_heap[k] for k in before_heap},
                     cpu_seconds={k:after_cpu[k]-before_cpu[k] for k in groups},
                     stall_fraction={k:(after_pressure[k]-before_pressure[k])/(seconds*1e6) for k in before_pressure},
                     completed_collection_overlaps=nondeferred_overlaps(state,command_unix,ended_unix))
            rows.append(row)
            (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(label,'command',round(seconds,4),'GoGC',row['heap_delta']['NumGC'],
                  'engine CPU',round(row['cpu_seconds']['engine'],4),
                  'completed collections overlapping command',len(row['completed_collection_overlaps']),flush=True)
    idle('final-teardown',quiet=False)
    action('mode',deferred=False,drain=True)
    final=get('snapshot-collection')
    (root/'final-collection-state.json').write_text(json.dumps(final,indent=2)+'\n')
    for row in rows:
        events=nondeferred_overlaps(final,row['command_unix_start'],row['command_unix_end'])
        row['all_collection_overlaps']=events
        row['collection_algorithm_ambiguous']=any(unix(e['start'])<row['selected_at'] for e in events)
        row['collection_overlap_seconds']=sum(max(0.,min(unix(e['end']),row['command_unix_end'])-max(unix(e['start']),row['command_unix_start'])) for e in events)
    (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
    measured=[r for r in rows if not r['warmup']]
    summary={arm:{'command_seconds':statistics.median(r['command_seconds'] for r in measured if r['arm']==arm),
                  'commands':sum(r['arm']==arm for r in measured),
                  'commands_overlapping_collection':sum(bool(r['all_collection_overlaps']) for r in measured if r['arm']==arm),
                  'commands_with_Go_GC':sum(r['heap_delta']['NumGC']>0 for r in measured if r['arm']==arm)} for arm in ['off','on','cargo']}
    savings=[next(r['command_seconds'] for r in measured if r['pair']==pair and r['arm']=='off')-next(r['command_seconds'] for r in measured if r['pair']==pair and r['arm']=='on') for pair in range(args.pairs)]
    summary['paired_dagger']={'median_saving_seconds':statistics.median(savings),'faster_pairs':sum(v>0 for v in savings),'pairs':args.pairs}
    summary['candidate_minus_cargo_seconds']=summary['on']['command_seconds']-summary['cargo']['command_seconds']
    summary['max_host_stall_fraction']={k:max(r['stall_fraction'][k] for r in measured) for k in measured[0]['stall_fraction'] if k.startswith('host.')}
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
finally:
    config.write_text(original_config)
    get('wcprof/enabled',b'off')
    action('mode',deferred=False,drain=True)
    source_mode(False)
    mode('batch-metadata',False)
    mode('attribute-array-decode',False)
    mode('containerd-root-dedup',False)
