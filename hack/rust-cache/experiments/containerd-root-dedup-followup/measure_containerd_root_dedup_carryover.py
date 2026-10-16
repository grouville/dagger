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
        mark = time.monotonic()
        time.sleep(1 if quiet else .1)
        after = pressure()
        elapsed = time.monotonic() - mark
        state = get('client-lifecycle')
        stalls = {k: (after[k] - before[k]) / (elapsed * 1e6) for k in before}
        admitted = not state.get('sessions') and state['active_requests'] == 0 and (not quiet or (stalls['host.io.some'] < .05 and stalls['engine.io.some'] < .01))
        with (root / 'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label, admitted=admitted, stall_fraction=stalls, seconds=time.monotonic() - started)) + '\n')
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


# A Williams square balances each factor combination and its immediate predecessor.
orders = [
    ['off-off', 'off-on', 'on-on', 'on-off'],
    ['off-on', 'on-off', 'off-off', 'on-on'],
    ['on-off', 'on-on', 'off-on', 'off-off'],
    ['on-on', 'off-off', 'on-off', 'off-on'],
]
rows = []
try:
    config.write_text(re.sub(r'source = "[^"]+"', 'source = "' + str(module) + '"', original_config, count=1))
    assert not get('wcprof/enabled')['global_enabled']
    assert get('scalar-array-restore')['enabled']
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    mode('direct-span-protobuf', False)
    mode('snapshot-completions', False)
    source_mode(True)
    idle('initial')
    action('mode', deferred=True, drain=True)
    metadata = dict(
        experiment='Preparation algorithm crossed with command-only algorithm; no concurrent containerd collection.',
        started_at=datetime.now(timezone.utc).isoformat(), pairs=args.pairs, profile=args.profile,
        force_go_gc=args.force_go_gc, files=1, engine_id=record['Id'], engine_started=record['State']['StartedAt'],
        module_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=module, text=True).strip(),
        command='check rust:packages/check', cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
        orders=orders, fresh_processes=True, engine_and_compiler_warm=True, telemetry_enabled=True,
        natural_containerd_collection_deferred=True, dagql_pruning_not_disabled=True,
        idle_collector_must_not_run_inside_command=True, post_admission_observations_excluded=False,
        cgroup_scope='docker_total overlaps engine and sibling exec; never add all three',
        initial_heap=heap())
    (root / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    for pair in range(-1, args.pairs):
        for combination in orders[pair % len(orders)]:
            preparation, command = combination.split('-')
            label = f'{pair}-{combination}'
            idle(label + '-before-preparation')
            mode('containerd-root-dedup', preparation == 'on')
            preparation_heap = heap()
            collect = action('collect')
            scratch = action('prepare', files=1)
            snapshot = scratch['snapshot_id']
            assert get('snapshot-collection?snapshot=' + snapshot)['snapshot_exists']
            path = source / 'leaf_1023/src/lib.rs'
            text, count = re.subn(r'pub const EDIT: u64 = \d+;', 'pub const EDIT: u64 = ' + str(secrets.randbits(48)) + ';', path.read_text())
            assert count == 1
            path.write_text(text)
            idle(label)
            if args.force_go_gc:
                with urllib.request.urlopen(debug + 'gc', data=b'', timeout=180) as response:
                    response.read()
            # The command flag is independent of the collector that prepared the heap.
            mode('containerd-root-dedup', command == 'on')
            if args.profile:
                profile_start()
            before_heap = heap()
            before_cpu = cpu()
            before_pressure = pressure()
            command_unix = time.time()
            started = time.monotonic()
            with (root / (label + '.log')).open('w') as output:
                result = subprocess.run([str(cli), 'check', 'rust:packages/check'], cwd=source, env=env, stdout=output, stderr=subprocess.STDOUT)
            seconds = time.monotonic() - started
            ended_unix = time.time()
            after_cpu = cpu()
            after_pressure = pressure()
            after_heap = heap()
            assert result.returncode == 0 and 'passed' in (root / (label + '.log')).read_text(), label
            if args.profile:
                profile_end(label)
            state = get('snapshot-collection?snapshot=' + snapshot)
            overlaps = nondeferred_overlaps(state, command_unix, ended_unix)
            assert not overlaps, (label, 'unexpected real collection during idle command', overlaps)
            assert state['snapshot_exists'] and state['deferred']
            idle(label + '-teardown', quiet=False)
            mode('containerd-root-dedup', preparation == 'on')
            drained = action('collect')
            final = get('snapshot-collection?snapshot=' + snapshot)
            assert not final['snapshot_exists'] and final['deferred']
            row = dict(pair=pair, label=label, preparation=preparation, command=command, warmup=pair < 0,
                       command_seconds=seconds, command_unix_start=command_unix,
                       before_preparation_heap=preparation_heap, before_heap=before_heap, after_heap=after_heap,
                       heap_delta={k: after_heap[k] - before_heap[k] for k in before_heap},
                       cpu_seconds={k: after_cpu[k] - before_cpu[k] for k in groups},
                       stall_fraction={k: (after_pressure[k] - before_pressure[k]) / (seconds * 1e6) for k in before_pressure},
                       prepare_collection=collect, scratch=scratch, drain=drained,
                       actual_collection_overlaps=overlaps, retained_scratch_after_command=True,
                       scratch_reclaimed_after_drain=True)
            rows.append(row)
            (root / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n')
            print(label, 'command', round(seconds, 4), 'GoGC', row['heap_delta']['NumGC'],
                  'heap', round(before_heap['HeapAlloc'] / 1e6), '->', round(after_heap['HeapAlloc'] / 1e6),
                  'engine CPU', round(row['cpu_seconds']['engine'], 4), flush=True)
    measured = [r for r in rows if not r['warmup']]
    summary = {}
    for first, second, factor in [('off-off', 'off-on', 'command_flag_after_off_preparation'),
                                  ('on-off', 'on-on', 'command_flag_after_on_preparation'),
                                  ('off-off', 'on-off', 'preparation_with_command_flag_off'),
                                  ('off-on', 'on-on', 'preparation_with_command_flag_on')]:
        arms = {label: [next(r for r in measured if r['pair'] == pair and r['preparation'] + '-' + r['command'] == label) for pair in range(args.pairs)] for label in [first, second]}
        savings = [a['command_seconds'] - b['command_seconds'] for a, b in zip(arms[first], arms[second])]
        summary[factor] = dict(before=first, after=second,
                              before_median_seconds=statistics.median(r['command_seconds'] for r in arms[first]),
                              after_median_seconds=statistics.median(r['command_seconds'] for r in arms[second]),
                              median_paired_saving_seconds=statistics.median(savings),
                              faster_pairs=sum(s > 0 for s in savings), pairs=args.pairs)
    summary['go_gc_command_count'] = sum(r['heap_delta']['NumGC'] > 0 for r in measured)
    summary['commands'] = len(measured)
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)
finally:
    config.write_text(original_config)
    get('wcprof/enabled', b'off')
    action('mode', deferred=False, drain=True)
    source_mode(False)
    mode('batch-metadata', False)
    mode('attribute-array-decode', False)
    mode('containerd-root-dedup', False)
