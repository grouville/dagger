import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import statistics
import subprocess
import time
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument('--pairs',type=int,default=8)
parser.add_argument('--output-root',required=True)
parser.add_argument('--cli',default='/tmp/rust-cache-sipsma-review/dagger-artifact-list-buffered')
parser.add_argument('--module',default='/tmp/dagger-rust-local-package-fingerprint')
parser.add_argument('--engine-binary',default='/tmp/rust-cache-sipsma-review/dagger-engine-compact-scalar-restore-v2')
parser.add_argument('--kinds',nargs='+',choices=['large_leaf','collection'],default=['large_leaf','collection'])
args=parser.parse_args()
base=Path('/tmp/rust-cache-sipsma-review');root=Path(args.output_root);root.mkdir(exist_ok=False)
modules={'before':args.module,'after':args.module,'cargo':'native cargo'}
physical={'before':'before','after':'before','cargo':'cargo'}
fixtures={size:{side:Path(f'/tmp/rust-native-config-entry-{size}-{side}') for side in ['before','cargo']} for size in ['1026','small']}
collector='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184'
collectors={side:collector for side in ['before','after']}
removed={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={key:value for key,value in os.environ.items() if key not in removed and not key.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL=collector,DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
toolchain=Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
with Path(args.engine_binary).open('rb') as binary_stream:binary_sha256=hashlib.file_digest(binary_stream,'sha256').hexdigest()
record=json.loads(subprocess.check_output(['docker','inspect','dagger-rust-parser-state-pool-oct14']))[0]
group=Path('/sys/fs/cgroup')/Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':',2)[2].strip().lstrip('/')
with urllib.request.urlopen('http://127.0.0.1:16104/debug/scalar-array-restore',timeout=5) as response:
    mode=json.load(response)
    assert mode['enabled'],mode
with urllib.request.urlopen('http://127.0.0.1:16104/debug/wcprof/enabled',timeout=5) as response:
    assert not json.load(response)['global_enabled']

def pressure():
    values = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', group)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                values[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return values

def engine_cpu_usage():
    for line in (group/'cpu.stat').read_text().splitlines():
        if line.startswith('usage_usec '):return int(line.split()[1])
    raise AssertionError('cgroup CPU counter missing')


def wait_for_idle(label):
    waiting = time.monotonic()
    while True:
        first = pressure()
        cpu_first = engine_cpu_usage()
        start = time.monotonic()
        time.sleep(1)
        after = pressure()
        cpu_seconds = (engine_cpu_usage()-cpu_first)/1e6
        seconds = time.monotonic()-start
        fractions = {key:(after[key]-first[key])/(seconds*1e6) for key in first}
        with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle',timeout=5) as response:
            state=json.load(response)
        idle=not state.get('sessions') and state['active_requests']==0
        admitted=idle and fractions['host.io.some']<.05 and fractions['engine.io.some']<.01 and fractions['host.cpu.some']<.10 and cpu_seconds/seconds<.05
        elapsed=time.monotonic()-waiting
        with (root/'admission.jsonl').open('a') as output:
            output.write(json.dumps(dict(label=label,window=seconds,seconds=elapsed,stall_fraction=fractions,engine_cpu_seconds=cpu_seconds,engines_idle=idle,admitted=admitted))+'\n')
        if admitted:return
        print('waiting for idle',label,round(elapsed,1),'seconds',flush=True)
        assert elapsed<60,'idle admission timed out; retain all measured observations'

def edit(kind, variant):
    size = 'small' if kind == 'collection' else ('1026' if kind in ['large_leaf', 'large_list'] else '130')
    relative = {'collection': 'app/src/lib.rs', 'leaf': 'leaf_0127/src/lib.rs', 'large_leaf': 'leaf_1023/src/lib.rs', 'large_list': 'leaf_1023/src/lib.rs'}[kind]
    pattern = r'pub fn edited_value\(\) -> u64 \{ \d+ \}' if kind == 'collection' else r'pub const EDIT: u64 = \d+;'
    value = secrets.randbits(48)
    replacement = f'pub fn edited_value() -> u64 {{ {value} }}' if kind == 'collection' else f'pub const EDIT: u64 = {value};'
    filename = fixtures[size][physical[variant]] / relative
    text, count = re.subn(pattern, replacement, filename.read_text())
    assert count == 1
    filename.write_text(text)

def set_metadata(enabled):
    request = urllib.request.Request('http://127.0.0.1:16104/debug/batch-metadata?enabled=' + str(enabled).lower(), data=b'', method='POST')
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.load(response)['enabled'] == enabled

def set_direct(enabled):
    request = urllib.request.Request('http://127.0.0.1:16104/debug/direct-span-protobuf?enabled=' + str(enabled).lower(), data=b'', method='POST')
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.load(response)['enabled'] == enabled

def source_mode(enabled):
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n' if enabled else b'off\n',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)

def invoke(kind, variant, label):
    if variant!='cargo':source_mode(variant=='after')
    size = 'small' if kind == 'collection' else ('1026' if kind in ['large_leaf', 'large_list'] else '130')
    source = fixtures[size][physical[variant]]
    if variant == 'cargo':
        run_env = dict(os.environ, RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'), CARGO_INCREMENTAL='1', CARGO_BUILD_JOBS='8', CARGO_TARGET_DIR=str(base / f'native-config-entry-{size}-cargo-target'))
        for key in ['RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_BUILD_DIR']:
            run_env.pop(key, None)
        command = [str(toolchain / 'cargo'), 'test' if kind == 'collection' else 'check', '--workspace', '--locked', '--offline']
        if kind == 'large_list':
            command = [str(toolchain / 'cargo'), 'metadata', '--no-deps', '--format-version=1', '--locked', '--offline']
    else:
        run_env = dict(env,DAGGER_CLOUD_URL=collectors[variant])
        selection = 'rust:packages/test' if kind == 'collection' else ('rust:packages/check' if kind == 'large_leaf' else 'rust:check')
        command = [args.cli, 'check', selection]
        if kind == 'large_list':
            command = [args.cli, 'check', '--list', '--all', 'rust:packages/check']
    wait_for_idle(label)
    edit(kind, variant)
    set_metadata(True)
    set_direct(False)
    cpu_before = engine_cpu_usage()
    before, started = pressure(), time.monotonic()
    with (root / (label + '.log')).open('w') as output:
        result = subprocess.run(command, cwd=source, env=run_env, stdout=output, stderr=subprocess.STDOUT)
    seconds = time.monotonic() - started
    after = pressure()
    cpu_after = engine_cpu_usage()
    assert not result.returncode, label
    log = (root / (label + '.log')).read_text()
    if variant != 'cargo':
        if kind == 'large_list':
            listed = re.findall(r'^rust\s+(\S+)\s+check$', log, re.M)
            expected = {'app', 'shared'} | {f'leaf_{i:04d}' for i in range(1024)}
            assert len(listed) == 1026 and set(listed) == expected, (label, 'incomplete listing', len(listed))
        else:
            assert 'passed' in log, label
    elif kind == 'large_list':
        assert len(json.loads(log)['packages']) == 1026,label
    elif kind != 'collection' and label.startswith('edited'):
        assert len(set(re.findall(r'Checking ([\w-]+) v', log))) == (2 if kind in ['leaf', 'large_leaf'] else 130), label
    with (root / 'pressure.jsonl').open('a') as output:
        output.write(json.dumps(dict(label=label, seconds=seconds, engine_cpu_seconds=(cpu_after-cpu_before)/1e6, stall_fraction={key: (after[key] - before[key]) / (seconds * 1e6) for key in before})) + '\n')
    return seconds

configs={fixtures[size]['before']/'dagger.toml':(fixtures[size]['before']/'dagger.toml').read_text() for size in ['1026','small']}
try:
    for config,original in configs.items():
        updated,count=re.subn(r'source = "[^"]+"',f'source = "{args.module}"',original,count=1);assert count==1;config.write_text(updated)
    for name,enabled in [('attribute-array-decode',True),('batch-metadata',True),('snapshot-completions',False),('direct-span-protobuf',False)]:
        request=urllib.request.Request(f'http://127.0.0.1:16104/debug/{name}?enabled={str(enabled).lower()}',data=b'',method='POST')
        with urllib.request.urlopen(request,timeout=5) as response:assert json.load(response)['enabled']==enabled
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    metadata=dict(mode='source snapshot seeds OFF/ON',startup_mode=mode,engine_binary=args.engine_binary,engine_binary_sha256=binary_sha256,engine_pid=record['State']['Pid'],same_volume=True,module=args.module,physical_sources={size:str(fixtures[size]['before']) for size in fixtures},native_cache_keys={size:f'native-config-entry-{size}-before' for size in fixtures},telemetry_enabled=True,collector=collector,batch_metadata=True,attribute_array_decoder=True,direct_span_protobuf=False,source_import_snapshot_seeds={'before':False,'after':True},snapshot_completions=False,wcprof=False,cohort_comparison='rotating paired comparisons on the same source and compiler-cache history',fresh_unique_used_edit_per_invocation=True,post_sample_exclusion=False,admission=dict(quiet_window_seconds=1,host_io_some_fraction_below=.05,engine_io_some_fraction_below=.01,host_cpu_some_fraction_below=.10,engine_cpu_seconds_per_second_below=.05,max_wait_seconds=60))
    (root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    for i in range(2):
        for kind in args.kinds:
            for variant in modules:print('prepare',i,kind,variant,invoke(kind,variant,f'prepare-{i}-{kind}-{variant}'),flush=True)
    rows={kind:[] for kind in args.kinds}
    for i in range(args.pairs):
        for kind in rows:
            order=[['before','after','cargo'],['after','cargo','before'],['cargo','before','after']][i%3]
            row={variant:invoke(kind,variant,f'edited-{i}-{kind}-{variant}') for variant in order}
            rows[kind].append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(kind,i,row,flush=True)
    summary={kind:{variant:statistics.median(row[variant] for row in samples) for variant in modules} for kind,samples in rows.items()}
    for kind,samples in rows.items():
        summary[kind]['paired_saving_seconds']=statistics.median(row['before']-row['after'] for row in samples)
        summary[kind]['faster_pairs']=sum(row['after']<row['before'] for row in samples)
        summary[kind]['pairs']=len(samples)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
finally:
    source_mode(False)
    for config,original in configs.items():config.write_text(original)
    for name in ['batch-metadata','attribute-array-decode','direct-span-protobuf']:
        request=urllib.request.Request(f'http://127.0.0.1:16104/debug/{name}?enabled=false',data=b'',method='POST')
        with urllib.request.urlopen(request,timeout=5) as response:assert not json.load(response)['enabled']
