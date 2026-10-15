import collections
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'config-plan-file-profile'
root.mkdir(exist_ok=False)

def debug(route, data=None):
    request = urllib.request.Request('http://127.0.0.1:16104/debug/wcprof/' + route, data=data)
    return urllib.request.urlopen(request, timeout=30)

with debug('enabled') as response:
    assert not json.load(response)['global_enabled']

@contextmanager
def modules():
    saved = {}
    try:
        for size in ['1026', 'small']:
            for variant, module in [('before', '/tmp/dagger-rust-config-entry-checksum'), ('after', '/tmp/dagger-rust-config-plan-file-transfer')]:
                config = Path(f'/tmp/rust-native-config-entry-{size}-{variant}/dagger.toml')
                saved[config] = config.read_text()
                text, count = re.subn(r'source = "[^"]+"', f'source = "{module}"', saved[config], count=1)
                assert count == 1
                config.write_text(text)
        yield
    finally:
        for config, text in saved.items():
            config.write_text(text)

record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
group = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
def io_state():
    pressure = {}
    for prefix, path in [('host', Path('/proc/pressure')), ('engine', group)]:
        for kind in ['cpu', 'io', 'memory']:
            for line in (path / (kind if prefix == 'host' else kind + '.pressure')).read_text().splitlines():
                pressure[prefix + '.' + kind + '.' + line.split()[0]] = int(line.split('total=')[1])
    return pressure

def invoke(size, variant, label):
    source = Path(f'/tmp/rust-native-config-entry-{size}-{variant}')
    relative = 'leaf_1023/src/lib.rs' if size == '1026' else 'app/src/lib.rs'
    filename = source / relative
    pattern = r'pub const EDIT: u64 = \d+;' if size == '1026' else r'pub fn edited_value\(\) -> u64 \{ \d+ \}'
    value = secrets.randbits(48)
    replacement = f'pub const EDIT: u64 = {value};' if size == '1026' else f'pub fn edited_value() -> u64 {{ {value} }}'
    text, count = re.subn(pattern, replacement, filename.read_text())
    assert count == 1
    filename.write_text(text)
    before = io_state()
    start = time.monotonic()
    with (root / (label + '.log')).open('w') as output:
        result = subprocess.run(['python3', str(base/'local_cli.py'), 'check', 'rust:check' if size == '1026' else 'rust:packages/test'], cwd=source, env=dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276'), stdout=output, stderr=subprocess.STDOUT)
    seconds = time.monotonic() - start
    after = io_state()
    assert not result.returncode, label
    return dict(seconds=seconds, stall_fraction={key: (after[key]-before[key])/(seconds*1e6) for key in before})

summaries = {}
with modules():
    for size in ['1026', 'small']:
        for variant in ['before', 'after']:
            invoke(size, variant, f'prepare-{size}-{variant}')
    for size, variants in [('1026', ['before','after','before','after','before','after']), ('small', ['before','after','before','after'])]:
        for index, variant in enumerate(variants):
            label = f'{size}-{index}-{variant}'
            debug('enabled', b'on').close()
            with debug('dump') as response:
                while response.read(1048576):
                    pass
            try:
                result = invoke(size, variant, label)
            finally:
                debug('enabled', b'off').close()
                with debug('dump') as response, (root/(label+'.ndjson')).open('wb') as output:
                    while data := response.read(1048576):
                        output.write(data)
            with (root/(label+'.ndjson')).open() as data:
                header = json.loads(next(data))
                assert not header['dropped_events'] and not header.get('open_ops'), header
                names = header['strings']
                ops = [dict(item, cls=names[item.get('c',0)], ident=names[item.get('i',0)]) for item in map(json.loads,data) if item['e']=='op']
            by = {op['id']:op for op in ops}
            requests = {}
            for op in ops:
                if op['k'] not in ['call','call_exec'] or op['cls'] not in ['File.contents','File.export']:
                    continue
                current = op
                while current.get('p') in by and current['cls'] != 'session.query':
                    current = by[current['p']]
                if current['cls']=='session.query':
                    requests[current['id']]=current
            classes = collections.defaultdict(lambda:dict(count=0,total_ms=0))
            for op in ops:
                cls = classes[op['k']+' '+op['cls']]
                cls['count']+=1
                cls['total_ms']+=(op['d']-op['s'])/1e6
            summaries[label]=dict(result,events=header['event_count'],dropped_events=header['dropped_events'],open_ops=header.get('open_ops',0),plan_requests=[dict(id=op['id'],ms=(op['d']-op['s'])/1e6) for op in requests.values()],classes=dict(classes))
            (root/'summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
            print(label, 'seconds',round(result['seconds'],3),'plan requests',summaries[label]['plan_requests'],flush=True)
print('PASS: fresh edit transport profiles; modules restored',flush=True)
