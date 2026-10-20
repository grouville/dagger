"""Create two matching stock engines; preserve every existing engine and volume."""
from pathlib import Path
import hashlib
import json
import subprocess
import time
import urllib.request

out = Path('/tmp/go-collection-upstream-review-oct19')
unit = Path('/tmp/go-collection-clean-branches')
original = json.loads((unit / 'main-engine.json').read_text())
binary = None
records = {}
for arm in ['main', 'candidate']:
    binary = out / ('config-dagql-main-engine' if arm == 'main' else 'config-dagql-dagql-engine')
    name = 'dagger-config-dagql-' + arm + '-oct19'
    assert not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'], text=True).strip()
    assert name not in subprocess.check_output(['docker', 'volume', 'ls', '--format', '{{.Name}}'], text=True).splitlines()
    command = ['docker', 'create', '--name', name, '--label', 'codex.task=go-listing-independent-review',
               '--privileged', '--env', 'GOMAXPROCS=8', '-p', '127.0.0.1::1234', '-p', '127.0.0.1::6060',
               '--mount', 'type=volume,source=' + name + ',target=/var/lib/dagger', original['image'],
               '--addr', 'tcp://0.0.0.0:1234', '--debugaddr', '0.0.0.0:6060']
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['docker', 'cp', str(binary), name + ':/usr/local/bin/dagger-engine'], check=True)
    subprocess.run(['docker', 'start', name], check=True, stdout=subprocess.DEVNULL)
    record = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
    ports = record['NetworkSettings']['Ports']
    info = dict(name=name, runner='tcp://127.0.0.1:' + ports['1234/tcp'][0]['HostPort'],
                debug='http://127.0.0.1:' + ports['6060/tcp'][0]['HostPort'], volume=name,
                base='ce6dc9f9403b52067f5831149eab4871f857185d', binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                image=original['image'], command=command, cache_policy_overrides=False)
    records[arm] = info
    (out / 'config-dagql-engines.json').write_text(json.dumps(records, indent=2) + '\n')
    for attempt in range(120):
        try:
            with urllib.request.urlopen(info['debug'] + '/debug/vars', timeout=1) as response:
                json.load(response)
            break
        except OSError:
            time.sleep(.25)
    else:
        raise RuntimeError('Engine did not become ready; retain it for diagnosis: ' + name)
    print(json.dumps(info), flush=True)
