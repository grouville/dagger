from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path(__file__).parent / 'correctness'
root.mkdir(exist_ok=False)
base = root.parent.parent
fixtures = base / 'rust-go-test-collections/fixtures'
module = Path('/tmp/dagger-rust-test-collection-batched-inputs')
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
    RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),
    RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',
    _EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
prefix = ['python3', str(base/'local_cli_collector.py')]
rows = []
def run(label, command, source, succeeds=True, diagnostic=None):
    started = time.monotonic()
    with (root/(label+'.log')).open('w') as out:
        result = subprocess.run(prefix+command, cwd=source, env=env, stdout=out, stderr=subprocess.STDOUT)
    rows.append(dict(label=label, exit_code=result.returncode, expected_success=succeeds,
        seconds=time.monotonic()-started, command=command))
    (root/'results.json').write_text(json.dumps(rows, indent=2)+'\n')
    assert (result.returncode == 0) == succeeds, label
    if diagnostic:
        assert diagnostic in (root/(label+'.log')).read_text(errors='replace'), label
    print(label, result.returncode, flush=True)
small = fixtures/'rust-1'
wide = fixtures/'rust-16'
files = [small/'dagger.toml', wide/'dagger.toml', small/'pkg_000/src/lib.rs', wide/'pkg_001/src/lib.rs']
saved = {f:f.read_bytes() for f in files}
import urllib.request
def candidate(enabled):
    request=urllib.request.Request('http://127.0.0.1:16104/debug/interface-field-snapshots?enabled='+str(enabled).lower(),data=b'')
    with urllib.request.urlopen(request,timeout=15) as response:assert json.load(response)['enabled']==enabled
try:
    candidate(True)
    for source in [small, wide]:
        config = source/'dagger.toml'
        config.write_text(config.read_text().replace('/tmp/dagger-rust-test-collection-granularity', str(module)))
    file = small/'pkg_000/src/lib.rs'
    original = file.read_text()
    old = 'fn test_001() { assert!(edited_value() > 0); }'
    assert old in original
    file.write_text(original.replace(old, 'fn test_001() { panic!("batched-inputs-sentinel"); }'))
    link = 'dag://?check=rust/packages/tests/test&rust-package=pkg_000'
    run('subset-excludes-poison', ['check', link+'&rust-test=src/lib.rs::test_000&rust-test=src/lib.rs::test_002'], small)
    run('subset-reports-poison', ['check', link+'&rust-test=src/lib.rs::test_001'], small, False, 'batched-inputs-sentinel')
    run('whole-package-reports-poison', ['check', 'rust:packages/tests/test'], small, False, 'batched-inputs-sentinel')
    file.write_text(original)
    run('whole-package-repaired', ['check', 'rust:packages/tests/test'], small)
    file = wide/'pkg_001/src/lib.rs'
    file.write_text('pub fn invalid() -> u64 { "excluded crate" }\n')
    run('package-filter-excludes-invalid-crate', ['check', 'dag://?check=rust/packages/tests/test&rust-package=pkg_000'], wide)
    run('whole-workspace-reports-invalid-crate', ['check', 'rust:packages/tests/test'], wide, False, 'mismatched types')
    file.write_bytes(saved[file])
    run('whole-workspace-repaired', ['check', 'rust:packages/tests/test'], wide)
    run('plain-workspace-api', ['api', 'call', 'rust', 'test', '--source', '.'], small)
finally:
    candidate(False)
    for file, contents in saved.items():
        file.write_bytes(contents)
