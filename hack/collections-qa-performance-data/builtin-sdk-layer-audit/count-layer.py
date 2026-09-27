"""Count one verified public SDK layer without extracting files or starting an engine."""
from pathlib import Path
from collections import Counter, defaultdict
import hashlib
import json
import subprocess
import tarfile
import time

P = Path(__file__).resolve().parent
CID = '247add71e960dffdd33b248d1d5503eec3b3a4340dae691f72c730d5eb7ed412'
manifest = json.loads((P / 'go-manifest.json').read_text())
desc = manifest['layers'][2]
assert desc['digest'] == 'sha256:44b3c4a427a9955d872d537b7405e032d3ab6edf926a7dfc781d3126c87f97c8'
info = json.loads(subprocess.check_output(['docker', 'inspect', CID], timeout=20))[0]
assert info['Id'] == CID and not info['State']['Running']
assert info['Config']['Labels']['dagger.perf.owner'] == 'collections-lazy-core-runtime-v1'
blob = P / 'go-toolchain-layer.private.zstd'
assert not blob.exists()
started = time.monotonic()
subprocess.run(['docker', 'cp', CID + ':/usr/local/share/dagger/content/blobs/sha256/' + desc['digest'][7:], str(blob)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
assert blob.stat().st_size == desc['size']
with blob.open('rb') as source:
    assert hashlib.file_digest(source, 'sha256').hexdigest() == desc['digest'][7:]
counts = defaultdict(Counter)
decoder = subprocess.Popen(['zstd', '-dc', str(blob)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
try:
    with tarfile.open(fileobj=decoder.stdout, mode='r|') as archive:
        total = 0
        for entry in archive:
            total += 1
            assert total <= 100000
            assert time.monotonic() - started < 60
            name = entry.name.removeprefix('./').lstrip('/')
            if name.startswith('usr/local/go/'):
                first = name[len('usr/local/go/'):].split('/')[0]
                category = first if first in ('api', 'bin', 'doc', 'lib', 'misc', 'pkg', 'src', 'test') else 'other-goroot'
            else:
                category = 'outside-goroot'
            row = counts[category]
            row['entries'] += 1
            if entry.isfile():
                row['files'] += 1
                row['file_bytes'] += entry.size
                if name.endswith('_test.go'):
                    row['test_go_files'] += 1
                    row['test_go_bytes'] += entry.size
                if '/testdata/' in name:
                    row['testdata_files'] += 1
                    row['testdata_bytes'] += entry.size
    assert decoder.wait(timeout=10) == 0
finally:
    if decoder.poll() is None:
        decoder.kill()
        decoder.wait()
    decoder.stdout.close()
    decoder.stderr.close()
result = {'compressed_digest': desc['digest'], 'compressed_bytes': desc['size'], 'categories': dict(counts), 'scope': 'Verified layer metadata only; no extraction, engine invocation, performance comparison or permission to remove any category.', 'elapsed_seconds': time.monotonic() - started}
(P / 'toolchain-population.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
