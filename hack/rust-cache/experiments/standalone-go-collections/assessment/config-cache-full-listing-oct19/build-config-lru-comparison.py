"""Build the original LRU patch on the same base as the DagQL comparison."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
import urllib.request

out = Path('/tmp/go-collection-upstream-review-oct19')
source = out / 'engine-config-cache-choice'
binary = out / 'config-comparison-lru-engine'
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
assert head == 'f2a21f27edf64b2d9a00e06e61ddb29e3a500292'
assert not subprocess.check_output(['git', 'diff', '--name-only'], cwd=source)
env = dict(os.environ, GOMAXPROCS='8', GOTOOLCHAIN='local', GOWORK='off',
           GOPROXY='off', GOSUMDB='off', CGO_ENABLED='0')
command = [go, 'build', '-p=2', '-buildvcs=false', '-o', str(binary), './cmd/engine']
start = time.monotonic()
with (out / 'config-comparison-lru-build.log').open('w') as log:
    result = subprocess.run(command, cwd=source, env=env, stdout=log,
                            stderr=subprocess.STDOUT, timeout=300)
record = dict(command=command, source=str(source), source_commit=head,
              base='ce6dc9f9403b52067f5831149eab4871f857185d',
              seconds=time.monotonic()-start, exit_code=result.returncode)
assert result.returncode == 0, record
record['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
engines = json.loads((out / 'config-dagql-engines.json').read_text())
name = 'dagger-config-lru-comparison-oct19'
assert not subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'], text=True).strip()
assert name not in subprocess.check_output(['docker', 'volume', 'ls', '--format', '{{.Name}}'], text=True).splitlines()
image = engines['main']['image']
create = ['docker', 'create', '--name', name, '--label', 'codex.task=go-listing-independent-review',
          '--privileged', '--env', 'GOMAXPROCS=8', '-p', '127.0.0.1::1234', '-p', '127.0.0.1::6060',
          '--mount', 'type=volume,source=' + name + ',target=/var/lib/dagger', image,
          '--addr', 'tcp://0.0.0.0:1234', '--debugaddr', '0.0.0.0:6060']
subprocess.run(create, check=True, stdout=subprocess.DEVNULL)
subprocess.run(['docker', 'cp', str(binary), name + ':/usr/local/bin/dagger-engine'], check=True)
subprocess.run(['docker', 'start', name], check=True, stdout=subprocess.DEVNULL)
info = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]
ports = info['NetworkSettings']['Ports']
record.update(name=name, runner='tcp://127.0.0.1:' + ports['1234/tcp'][0]['HostPort'],
              debug='http://127.0.0.1:' + ports['6060/tcp'][0]['HostPort'],
              volume=name, image=image, create_command=create, cache_policy_overrides=False)
(out / 'config-comparison-lru-engine.json').write_text(json.dumps(record, indent=2) + '\n')
for attempt in range(120):
    try:
        with urllib.request.urlopen(record['debug'] + '/debug/vars', timeout=1) as response:
            json.load(response)
        break
    except OSError:
        time.sleep(.25)
else:
    raise RuntimeError('Engine did not become ready; retained for diagnosis: ' + name)
print(json.dumps(record), flush=True)
