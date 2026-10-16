from pathlib import Path
import argparse
import itertools
import json
import os
import random
import re
import secrets
import statistics
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--sizes', nargs='+', type=int, default=[1, 16, 64])
parser.add_argument('--pairs', type=int, default=4)
parser.add_argument('--seed', type=int, default=2026101619)
args = parser.parse_args()
root = args.output
root.mkdir(exist_ok=False)
base = Path('/tmp/rust-cache-sipsma-review')
home = Path(__file__).parent
debug = 'http://127.0.0.1:16104/debug/'
cli = base/'dagger-artifact-list-buffered'
go = Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go')
rust = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
def get(route, data=None):
    with urllib.request.urlopen(urllib.request.Request(debug+route, data=data), timeout=30) as response:
        return json.load(response)
def mode(route, enabled):
    assert get(route+'?enabled='+str(enabled).lower(), b'')['enabled'] == enabled
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
cgroup = Path('/sys/fs/cgroup')/Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
def pressure():
    result = {}
    for name, path in [('host', Path('/proc/pressure')), ('engine', cgroup)]:
        for kind in ['cpu', 'io', 'memory']:
            filename = path/(kind if name == 'host' else kind+'.pressure')
            for line in filename.read_text().splitlines(): result[name+'.'+kind+'.'+line.split()[0]] = int(line.split('total=')[1])
    return result
def cpu():
    return int(next(line.split()[1] for line in (cgroup/'cpu.stat').read_text().splitlines() if line.startswith('usage_usec ')))/1e6
def heap():
    return {k: v for k,v in get('vars')['memstats'].items() if k in ['HeapAlloc','TotalAlloc','NumGC','Mallocs','PauseTotalNs']}
def idle(label):
    tick = time.monotonic()
    while True:
        before = pressure(); before_cpu = cpu(); mark = time.monotonic(); time.sleep(1)
        delta = time.monotonic()-mark; after = pressure(); state = get('client-lifecycle')
        quiet = not state.get('sessions') and state['active_requests']==0 and (after['host.io.some']-before['host.io.some'])/(delta*1e6)<.05 and (cpu()-before_cpu)/delta<.15
        with (root/'admission.jsonl').open('a') as out: out.write(json.dumps(dict(label=label,seconds=time.monotonic()-tick,admitted=quiet))+'\n')
        if quiet:return
        assert time.monotonic()-tick<120,'admission timeout'
removed = {'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env = {k:v for k,v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276',_EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
fixtures = [f for f in json.loads((home/'fixtures.json').read_text()) if f['packages'] in args.sizes]
for fixture in fixtures:
    if fixture['language']=='rust':
        config=Path(fixture['source'])/'dagger.toml'
        config.write_text(config.read_text().replace('/tmp/dagger-rust-native-discovery-current','/tmp/dagger-rust-test-collection-granularity'))
orders={};rng=random.Random(args.seed)
for fixture in fixtures:
    name=fixture['language']+'-'+str(fixture['packages'])
    all_orders=list(itertools.permutations(['batch','collection','native']))
    choices=[list(rng.choice([o for o in all_orders if (o.index('batch')<o.index('collection')) == (i%2==0)])) for i in range(args.pairs)]
    rng.shuffle(choices);orders[name]=choices
metadata=dict(seed=args.seed,pairs=args.pairs,orders=orders,engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],go_revision='334136faaa1cd36ac26dfdc648eda907ce99c063',rust_branch='experiment/test-collection-granularity',telemetry_enabled=True,profiling=False,natural_gc=True,fresh_edit_every_arm=True,eight_real_unit_tests_per_package=True,doc_tests_disabled_in_timing_fixture=True,compiler_and_engine_warm=True,fixtures=fixtures)
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
rows=[]
try:
    assert not get('wcprof/enabled')['global_enabled']
    assert not get('layercopy-known-dirs')['enabled']
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    for fixture in fixtures:
        language=fixture['language'];count=fixture['packages'];name=language+'-'+str(count)
        for pair in range(-1,args.pairs):
            for arm in (['batch','collection','native'] if pair<0 else orders[name][pair]):
                label=f'{name}-{pair}-{arm}';file=Path(fixture['edit_file']);value=secrets.randbits(48)+1
                if language=='rust':pattern=r'pub fn edited_value\(\) -> u64 \{ \d+ \}';replacement=f'pub fn edited_value() -> u64 {{ {value} }}'
                else:pattern=r'func EditedValue\(\) uint64 \{ return \d+ \}';replacement=f'func EditedValue() uint64 {{ return {value} }}'
                text,changed=re.subn(pattern,replacement,file.read_text());assert changed==1;file.write_text(text)
                run_env=dict(env)
                if arm=='native':
                    if language=='rust':
                        run_env.update(RUSTC=str(rust/'rustc'),RUSTDOC=str(rust/'rustdoc'),CARGO_BUILD_JOBS='8',CARGO_INCREMENTAL='1',CARGO_TARGET_DIR=str(home/f'native-rust-{count}-target'))
                        for key in ['RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS']:run_env.pop(key,None)
                        command=[str(rust/'cargo'),'test','--workspace','--locked','--offline']
                    else:
                        run_env.update(CGO_ENABLED='0',GOMAXPROCS='8',GOCACHE=str(home/'native-go-cache'))
                        command=[str(go),'test','-p=8','./...']
                elif language=='rust':command=[str(cli),'check','rust:test' if arm=='batch' else 'rust:packages/tests/test']
                elif arm=='batch':command=[str(cli),'api','call','go','module','--path=.','test']
                else:command=[str(cli),'check','go:packages/tests/test']
                idle(label);before_pressure=pressure();before_heap=heap();before_cpu=cpu();tick=time.monotonic();started=time.time()
                with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,cwd=fixture['source'],env=run_env,stdout=out,stderr=subprocess.STDOUT)
                seconds=time.monotonic()-tick;ended=time.time();after_cpu=cpu();after_heap=heap();after_pressure=pressure()
                row=dict(label=label,language=language,packages=count,pair=pair,warmup=pair<0,arm=arm,seconds=seconds,exit_code=r.returncode,edit_value=value,command=command,engine_cpu=after_cpu-before_cpu,heap_delta={k:after_heap[k]-before_heap[k] for k in before_heap},pressure={k:(after_pressure[k]-before_pressure[k])/(seconds*1e6) for k in before_pressure},unix_start=started,unix_end=ended)
                with (root/'attempts.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
                assert r.returncode==0,(label,r.returncode)
                log=(root/(label+'.log')).read_text(errors='replace')
                if arm=='native':
                    if language=='rust':assert len(re.findall(r'test result: ok\. 8 passed',log))==count,(label,'wrong Rust test count')
                    else:assert len(re.findall(r'^ok\s+example.com/testcollections/',log,re.M))==count,(label,'wrong Go package count')
                rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
                print(label,round(seconds,4),'CPU',round(row['engine_cpu'],3),flush=True)
    summaries={}
    for fixture in fixtures:
        name=fixture['language']+'-'+str(fixture['packages']);data=[r for r in rows if r['language']==fixture['language'] and r['packages']==fixture['packages'] and not r['warmup']]
        arms={arm:[r for r in data if r['arm']==arm] for arm in ['batch','collection','native']}
        overheads=[arms['collection'][i]['seconds']-arms['batch'][i]['seconds'] for i in range(args.pairs)]
        summaries[name]=dict(median_seconds={arm:statistics.median(r['seconds'] for r in values) for arm,values in arms.items()},median_collection_minus_batch=statistics.median(overheads),collection_slower_pairs=sum(d>0 for d in overheads),pairs=args.pairs,median_engine_allocated_bytes={arm:statistics.median(r['heap_delta']['TotalAlloc'] for r in values) for arm,values in arms.items()})
    (root/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n');print(json.dumps(summaries,indent=2),flush=True)
finally:
    mode('batch-metadata',False);mode('attribute-array-decode',False)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True)
