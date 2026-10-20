"""Run the identical focused integration binary against each engine."""
from pathlib import Path
import json
import os
import subprocess
import time

root = Path(__file__).resolve().parent
engines = json.loads((root / 'engines.json').read_text())
results = []
for arm in ['main', 'engine']:
    env = dict(os.environ,
               _EXPERIMENTAL_DAGGER_CLI_BIN=str((root / 'bin/dagger').resolve()),
               RUST_CACHE_BENCH_CLI='/tmp/generate-14184-review/bin/changeset-integration.test',
               RUST_CACHE_BENCH_RUNNER=engines[arm]['runner'], GOMAXPROCS='4')
    command = ['python3', '/tmp/rust-cache-sipsma-review/local_cli_collector.py',
               '-test.v', '-test.parallel=1', '-test.timeout=90s',
               '-test.run=^TestChangeset$/^TestSingleChangesetPreservesSnapshots$']
    started = time.monotonic()
    with (root / ('api-' + arm + '.log')).open('w') as log:
        result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
    row = dict(arm=arm, engine=engines[arm]['name'], exit_code=result.returncode,
               seconds=time.monotonic()-started, command=command)
    results.append(row)
    (root / 'api-results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(row), flush=True)
