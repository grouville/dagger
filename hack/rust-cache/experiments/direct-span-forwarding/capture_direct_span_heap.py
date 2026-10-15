import json
from pathlib import Path
import subprocess
import time
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'direct-spans-memory'
root.mkdir(exist_ok=False)
record = json.loads(subprocess.check_output(['docker', 'inspect', 'dagger-rust-parser-state-pool-oct14']))[0]
group = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')

def cpu():
    return int(dict(line.split() for line in (group / 'cpu.stat').read_text().splitlines())['usage_usec'])

def get(path, timeout=45):
    return urllib.request.urlopen('http://127.0.0.1:16104/debug/' + path, timeout=timeout)

started = time.monotonic()
while True:
    before = cpu()
    time.sleep(1)
    with get('client-lifecycle') as response:
        lifecycle = json.load(response)
    if not lifecycle.get('sessions') and not lifecycle['active_requests'] and (cpu() - before) < 50000:
        break
    assert time.monotonic() - started < 60, 'engine is not idle; no forced collection yet'

observations = dict(engine='dagger-rust-parser-state-pool-oct14',
    memory_limit=record['HostConfig']['Memory'], memory_swap=record['HostConfig']['MemorySwap'],
    cache_volume_preserved=True, no_active_sessions=True,
    diagnostic_only=True, after_all_latency_measurements=True, captures=[])
for label, endpoint in [('unforced', 'pprof/heap'), ('after-gc', 'pprof/heap?gc=1')]:
    started = time.monotonic()
    with get(endpoint) as response:
        (root / (label + '.pprof')).write_bytes(response.read())
    observations['captures'].append(dict(label=label, seconds=time.monotonic()-started, forced_gc=label=='after-gc'))
    print('PASS heap capture', label, flush=True)
(root/'metadata.json').write_text(json.dumps(observations, indent=2) + '\n')
for label in ['unforced', 'after-gc']:
    for sample in ['inuse_space', 'inuse_objects', 'alloc_space']:
        for cumulative in [False, True]:
            options=['-top', '-nodecount=30', '-sample_index='+sample] + (['-cum'] if cumulative else [])
            with (root / (label+'-'+sample+('-cum' if cumulative else '-flat')+'.txt')).open('w') as output:
                subprocess.run(['/home/dagger/.local/bin/go', 'tool', 'pprof', *options,
                    str(base/'dagger-engine-direct-span-protobuf'), str(root/(label+'.pprof'))],
                    stdout=output, stderr=subprocess.STDOUT, check=True)
print('PASS heap summaries; no engine settings changed', flush=True)
