"""Build a matching current-main CLI/engine and retain a separate engine."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
import urllib.request

out = Path('/tmp/go-listing-current-main-oct20')
identity = json.loads((out / 'identities.json').read_text())
source = out / 'engine-main'
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env = dict(os.environ, GOMAXPROCS='8', GOTOOLCHAIN='local', GOWORK='off',
           GOPROXY='off', GOSUMDB='off', CGO_ENABLED='0')
rows = []
for name, target in [('engine', './cmd/engine'), ('cli', './cmd/dagger')]:
    binary = out / ('main-' + name)
    command = [go, 'build', '-p=2', '-buildvcs=false', '-o', str(binary), target]
    start = time.monotonic()
    print(json.dumps(dict(event='build-start', name=name)), flush=True)
    with (out / (name + '-build.log')).open('w') as log:
        result = subprocess.run(command, cwd=source, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=360)
    row = dict(name=name, base=identity['engine_main'], command=command,
               seconds=time.monotonic()-start, exit_code=result.returncode)
    if result.returncode == 0:
        row['sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
    rows.append(row)
    (out / 'builds.json').write_text(json.dumps(rows, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    assert result.returncode == 0
version = subprocess.check_output([str(out / 'main-cli'), 'version'], text=True).strip()
name = 'dagger-go-current-main-oct20'
image = 'sha256:af521f4adb6de430d63a79b4c14dbd162e21c7e6d0cf207f7dcfbf716857c370'
assert not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'], text=True).strip()
assert name not in subprocess.check_output(['docker', 'volume', 'ls', '--format', '{{.Name}}'], text=True).splitlines()
command = ['docker', 'create', '--name', name, '--label', 'codex.task=go-listing-independent-review',
           '--privileged', '--env', 'GOMAXPROCS=8', '-p', '127.0.0.1::1234', '-p', '127.0.0.1::6060',
           '--mount', 'type=volume,source=' + name + ',target=/var/lib/dagger', image,
           '--addr', 'tcp://0.0.0.0:1234', '--debugaddr', '0.0.0.0:6060']
subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
subprocess.run(['docker', 'cp', str(out / 'main-engine'), name + ':/usr/local/bin/dagger-engine'], check=True)
subprocess.run(['docker', 'start', name], check=True, stdout=subprocess.DEVNULL)
record = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
ports = record['NetworkSettings']['Ports']
info = dict(name=name, base=identity['engine_main'], image=image, volume=name,
            cli_version=version, cli_sha256=rows[1]['sha256'], engine_sha256=rows[0]['sha256'],
            runner='tcp://127.0.0.1:' + ports['1234/tcp'][0]['HostPort'],
            debug='http://127.0.0.1:' + ports['6060/tcp'][0]['HostPort'], command=command,
            cache_policy_overrides=False)
(out / 'engine.json').write_text(json.dumps(info, indent=2)+'\n')
for attempt in range(120):
    try:
        with urllib.request.urlopen(info['debug'] + '/debug/vars', timeout=1) as response:
            json.load(response)
        break
    except OSError:
        time.sleep(.25)
else:
    raise RuntimeError('Engine not ready; retained for diagnosis: ' + name)
print(json.dumps(info), flush=True)
