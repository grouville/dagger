"""New engines only; keep all previous engines and every volume."""
from pathlib import Path
import hashlib
import json
import subprocess
import time
import urllib.request

root = Path(__file__).resolve().parent
image = json.loads(Path('/tmp/go-listing-current-main-oct20/engine.json').read_text())['image']
engines = {}
for arm in ['main', 'candidate']:
    name = 'dagger-generate-core-final-' + arm + '-oct20'
    assert not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'], text=True).strip()
    assert name not in subprocess.check_output(['docker', 'volume', 'ls', '--format', '{{.Name}}'], text=True).splitlines()
    command = ['docker', 'create', '--name', name, '--label', 'codex.task=generate-14184-review',
               '--privileged', '--cpus', '4', '--env', 'GOMAXPROCS=4',
               '-p', '127.0.0.1::1234', '-p', '127.0.0.1::6060',
               '--mount', 'type=volume,source=' + name + ',target=/var/lib/dagger', image,
               '--addr', 'tcp://0.0.0.0:1234', '--debugaddr', '0.0.0.0:6060']
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['docker', 'cp', str((root / ('bin/engine-candidate' if arm == 'candidate' else 'bin/engine-main')).resolve()), name + ':/usr/local/bin/dagger-engine'], check=True)
    subprocess.run(['docker', 'start', name], check=True, stdout=subprocess.DEVNULL)
    record = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
    ports = record['NetworkSettings']['Ports']
    info = dict(name=name, arm=arm, base='35b97b7e55abd108f2d10255f709afc82f00175d', image=image,
                volume=name, cpus=4, cli_path=str(root / ('bin/dagger')), cache_policy_overrides=False,
                engine_sha256=hashlib.sha256((root / ('bin/engine-candidate' if arm == 'candidate' else 'bin/engine-main')).read_bytes()).hexdigest(),
                runner='tcp://127.0.0.1:' + ports['1234/tcp'][0]['HostPort'],
                debug='http://127.0.0.1:' + ports['6060/tcp'][0]['HostPort'], command=command)
    engines[arm] = info
    (root / 'engines.json').write_text(json.dumps(engines, indent=2) + '\n')
    for attempt in range(120):
        try:
            with urllib.request.urlopen(info['debug'] + '/debug/vars', timeout=1) as response:
                json.load(response)
            break
        except OSError:
            time.sleep(.25)
    else:
        raise RuntimeError('Retained engine not ready: ' + name)
    print(json.dumps(info), flush=True)
