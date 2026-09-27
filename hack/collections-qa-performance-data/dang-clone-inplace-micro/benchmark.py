"""Compile two matched library binaries, then three alternating local cycles."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import time

H = Path(__file__).resolve().parent
ROOT = Path('/tmp/collections-perf/syntax-isolated/dang')
MODULE = Path('/tmp/dagger-go-kyle-latest')
GO = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
parser = argparse.ArgumentParser()
parser.add_argument('stage', choices=('build', 'measure'))
args = parser.parse_args()
assert len(json.loads((H / 'validation-results.json').read_text())) == 3
assert all(row['exit_code'] == 0 for row in json.loads((H / 'validation-results.json').read_text()))
env = {'GOMAXPROCS': '4', 'GOTOOLCHAIN': 'local', 'GOENV': 'off', 'GOFLAGS': '', 'GOPROXY': 'off', 'GOSUMDB': 'off', 'CGO_ENABLED': '0', 'DAGGER_DANG_BENCH_ROOT': str(MODULE)}
if args.stage == 'build':
    assert not (H / 'benchmark-builds.json').exists()
    manifest = {'baseline_sha256': sha(H / 'parse_cache.baseline.go'), 'candidate_sha256': sha(H / 'parse_cache.go'), 'fixed_environment': env, 'source_inputs': {str(p): sha(p) for p in H.iterdir() if p.suffix in ('.go', '.py') or p.name.endswith('-overlay.json')}, 'module_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=MODULE, text=True).strip(), 'module_sources': {str(MODULE / n): sha(MODULE / n) for n in ('go.dang', 'gomod/main.dang', '.dagger/modules/go-dev/main.dang')}, 'builds': []}
    for variant in ('baseline', 'candidate'):
        binary = H / (variant + '.test')
        command = [GO, 'test', '-mod=readonly', '-overlay=' + str(H / (variant + '-overlay.json')), '-c', '-o', str(binary), './pkg/dang']
        log = H / (variant + '-build.log')
        start = time.monotonic()
        with log.open('wb') as stream:
            proc = subprocess.run(command, cwd=ROOT, env={**os.environ, **env}, stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        row = {'variant': variant, 'command': command, 'exit_code': proc.returncode, 'seconds': time.monotonic() - start, 'log_sha256': sha(log), 'binary': str(binary), 'binary_sha256': sha(binary) if proc.returncode == 0 else None}
        manifest['builds'].append(row)
        (H / 'benchmark-builds.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(row), flush=True)
        assert proc.returncode == 0
else:
    assert not (H / 'benchmark-runs.json').exists()
    manifest = json.loads((H / 'benchmark-builds.json').read_text())
    assert len(manifest['builds']) == 2 and all(row['exit_code'] == 0 for row in manifest['builds'])
    rows = []
    for cycle in range(3):
        for variant in (('baseline', 'candidate') if cycle % 2 == 0 else ('candidate', 'baseline')):
            for group in ('source_inputs', 'module_sources'):
                for path, expected in manifest[group].items():
                    assert sha(path) == expected, path
            build = next(row for row in manifest['builds'] if row['variant'] == variant)
            assert sha(build['binary']) == build['binary_sha256']
            command = [build['binary'], '-test.run=^(TestCloneSyntaxLeaves.*|TestCloneSyntaxInPlace.*)$', '-test.bench=^BenchmarkCloneSyntaxLeaves(Mutable|Module)?$', '-test.benchmem', '-test.benchtime=200ms', '-test.count=1', '-test.timeout=90s']
            log = H / ('bench-%d-%s.log' % (cycle, variant))
            start = time.monotonic()
            with log.open('wb') as stream:
                proc = subprocess.run(command, cwd=ROOT, env={**os.environ, **env}, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
            row = {'cycle': cycle, 'variant': variant, 'command': command, 'exit_code': proc.returncode, 'seconds': time.monotonic() - start, 'log_sha256': sha(log)}
            rows.append(row)
            (H / 'benchmark-runs.json').write_text(json.dumps(rows, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            assert proc.returncode == 0
