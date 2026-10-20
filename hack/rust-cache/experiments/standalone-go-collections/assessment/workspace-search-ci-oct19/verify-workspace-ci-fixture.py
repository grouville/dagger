"""Check the CI-compatible search fixture on unchanged and patched engines."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import time

out = Path('/tmp/go-collection-upstream-review-oct19')
parser = argparse.ArgumentParser()
parser.add_argument('--only-fix', action='store_true')
args = parser.parse_args()
binary = out / 'workspace-overlay-ci-integration.test'
clients = {'main': '/tmp/go-collection-clean-branches/main-dagger',
           'fix': str(out / 'workspace-overlay-ci-dagger')}
fixed = json.loads((out / 'workspace-overlay-engine.json').read_text())
records = ([row for row in json.loads((out / 'workspace-overlay-ci-results.json').read_text()) if row['arm'] == 'main']
           if args.only_fix else [])
for arm, runner in [('main', 'tcp://127.0.0.1:16310'), ('fix', fixed['runner'])]:
    if args.only_fix and arm == 'main':
        continue
    cli = clients[arm]
    env = dict(os.environ, GOMAXPROCS='8', RUST_CACHE_BENCH_RUNNER=runner,
               RUST_CACHE_BENCH_CLI=str(binary), _EXPERIMENTAL_DAGGER_CLI_BIN=cli,
               RUST_CACHE_BENCH_COLLECTOR='http://' + Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip() + ':43184')
    log = out / ('workspace-overlay-ci-' + arm + '.log')
    command = ['python3', '/tmp/rust-cache-sipsma-review/local_cli_collector.py',
               '-test.v', '-test.count=1', '-test.parallel=1', '-test.timeout=240s',
               '-test.run=^TestWorkspaceAPI/(TestHostWorkspaceOverlaySearchPaths|TestHostWorkspaceOverlaySearchAndGlob)$']
    started = time.monotonic()
    with log.open('w') as output:
        result = subprocess.run(command, env=env, cwd=out / 'engine-workspace-overlay',
                                stdout=output, stderr=subprocess.STDOUT, timeout=270)
    text = log.read_text()
    failures = [line.strip() for line in text.splitlines() if '--- FAIL:' in line]
    records.append(dict(arm=arm, runner=runner, command=command, log=str(log),
                        exit_code=result.returncode, seconds=time.monotonic() - started,
                        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                        cli=cli, cli_sha256=hashlib.sha256(Path(cli).read_bytes()).hexdigest(),
                        failing_tests=failures))
    (out / 'workspace-overlay-ci-results.json').write_text(json.dumps(records, indent=2) + '\n')
    print(json.dumps(records[-1]), flush=True)
    assert 'search: grep error:' not in text, text[-4000:]
    if arm == 'main':
        assert result.returncode != 0, text[-4000:]
        assert sum('--- FAIL: TestWorkspaceAPI/TestHostWorkspaceOverlaySearchPaths/' in line for line in failures) == 3, failures
        assert '--- PASS: TestWorkspaceAPI/TestHostWorkspaceOverlaySearchPaths/unrelated_missing_path' in text
        assert '--- PASS: TestWorkspaceAPI/TestHostWorkspaceOverlaySearchAndGlob ' in text
    else:
        assert result.returncode == 0, text[-4000:]
        assert sum('--- PASS: TestWorkspaceAPI/TestHostWorkspaceOverlaySearchPaths/' in line for line in text.splitlines()) == 4
        assert sum('--- PASS: TestWorkspaceAPI/TestHostWorkspaceOverlaySearchAndGlob/' in line for line in text.splitlines()) == 3
