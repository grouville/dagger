from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

H = Path(__file__).resolve().parent
ROOT = Path('/tmp/collections-perf/syntax-isolated/dang')
GO = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (H / 'validation-results.json').exists()
env = {'GOMAXPROCS': '4', 'GOTOOLCHAIN': 'local', 'GOENV': 'off', 'GOFLAGS': '', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'CGO_ENABLED': '0'}
pattern = '^(TestCloneSyntaxLeaves.*|TestCloneSyntaxInPlace.*|TestSyntaxCache.*)$'
manifest = {'baseline_sha256': sha(H / 'parse_cache.baseline.go'), 'candidate_sha256': sha(H / 'parse_cache.go'), 'go': {'path': GO, 'sha256': sha(GO)}, 'cwd': str(ROOT), 'fixed_environment': env, 'source_inputs': {str(p): sha(p) for p in H.iterdir() if p.suffix in ('.go', '.json', '.py', '.patch')}, 'module_inputs': {str(ROOT / n): sha(ROOT / n) for n in ('go.mod', 'go.sum')}, 'scope': 'Library-only clone visitor comparison against the effective retained scalar/nil baseline; no engine, Cloud or evaluated-state reuse.'}
(H / 'validation-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
results = []
for label, variant, race in [('baseline-normal', 'baseline', False), ('candidate-normal', 'candidate', False), ('candidate-race', 'candidate', True)]:
    command = [GO, 'test', '-mod=readonly', '-overlay=' + str(H / (variant + '-overlay.json'))]
    if race:
        command.append('-race')
    command += ['./pkg/dang', '-run', pattern, '-count=1', '-timeout=120s']
    output = H / (label + '.log')
    start = time.monotonic()
    fixed = {**env, 'CGO_ENABLED': '1' if race else '0'}
    with output.open('wb') as stream:
        proc = subprocess.run(command, cwd=ROOT, env={**os.environ, **fixed}, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
    row = {'label': label, 'command': command, 'fixed_environment': fixed, 'exit_code': proc.returncode, 'seconds': time.monotonic() - start, 'log_sha256': sha(output)}
    results.append(row)
    (H / 'validation-results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(row), flush=True)
    assert proc.returncode == 0, 'test failed: ' + label
