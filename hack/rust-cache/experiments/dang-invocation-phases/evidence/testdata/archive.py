from pathlib import Path
import gzip
import hashlib
import json

base = Path('/tmp/rust-cache-sipsma-review')
source = Path(__file__).parent
dest = Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/dang-invocation-phases')
dest.mkdir(exist_ok=False)
records, omissions = [], []

def copy(src, target):
    data = src.read_bytes()
    compress = src.suffix not in ['.gz', '.pprof', '.go', '.py', '.mod', '.sum', '.patch', '.dang'] and len(data) > 4096
    if compress:
        target = target.with_name(target.name+'.gz')
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = gzip.compress(data, compresslevel=6, mtime=0) if compress else data
    target.write_bytes(encoded)
    records.append(dict(path=str(target.relative_to(dest)), source=str(src), source_bytes=len(data),
        source_sha256=hashlib.sha256(data).hexdigest(), bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(), gzip=compress))

for src in sorted(source.rglob('*')):
    if not src.is_file() or '__pycache__' in src.parts:
        continue
    if src.name in ['dagger-engine', 'wcprof-complete.ndjson']:
        omissions.append(dict(source=str(src), bytes=src.stat().st_size,
            sha256=hashlib.sha256(src.read_bytes()).hexdigest(),
            reason='Executable or merged derivation; build inputs and raw profiling chunks retained.'))
        continue
    copy(src, dest/'evidence/testdata'/src.relative_to(source))

overlay = json.loads((source/'engine-overlay.json').read_text())['Replace']
overlay_sources = []
for index, (virtual, actual) in enumerate(sorted(overlay.items())):
    src = Path(actual)
    target = dest/'engine-overlay/testdata'/f'{index:03d}'/src.name
    copy(src, target)
    overlay_sources.append(dict(virtual=virtual, actual=actual, archived=str(target.relative_to(dest)),
        sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
(dest/'engine-overlay-manifest.json').write_text(json.dumps(overlay_sources, indent=2)+'\n')
for name in ['restart_owned_engine_clean.py', 'rust-go-test-collections/measure.py', 'interface-field-snapshots/verify_retained.py']:
    copy(base/name, dest/'protocol/testdata'/Path(name).name)
for name in ['module_git_clients.go', 'modfunc.go', 'workspace/git_clients.go', 'workspace/sdk_scopes.go', 'workspace/config.go', 'workspace/config_diagnostics.go']:
    copy(Path('/tmp/dagger-filesync-snapshot-seeds/core')/name, dest/'reference/testdata'/name)
for name in ['go.dang', 'gomod/main.dang', 'dagger-module.toml']:
    src = Path('/tmp/dagger-go-module-test-name-index')/name
    if src.exists():
        copy(src, dest/'module-source/testdata'/name)
(dest/'archive-manifest.json').write_text(json.dumps(records, indent=2)+'\n')
(dest/'omissions.json').write_text(json.dumps(omissions, indent=2)+'\n')
(dest/'.gitattributes').write_text('# Preserve captured source and logs exactly.\n**/testdata/** -whitespace\n')
(dest/'README.md').write_text('''# Invocation phase profile

See [the report](../../NATIVE_DANG_API_REQUEST_PROFILE.md). This is diagnostic evidence, not a latency improvement. The original HTTP/GraphQL client and engine pipeline remain in use; the wrapper only records the caller's synchronous API processing. Every API operation is verified to be parented under function evaluation.

The archive retains source, attribution tests, SDK tests/race results, complete engine overlays, a successful 4,398-row command, raw wcprof chunks, CPU windows, derivation commands, restart/retention checks and restored state. The large merged wcprof file is omitted with its hash; concatenate raw events with the final string table to reconstruct it. The binary is omitted with its hash and build command. The unchanged pinned SDK source is identified by the inventory in ../otel-evicted-queue/; the shared modfile used for this build is archived there too.

The CPU capture covers 50.04 seconds and includes roughly 4.5 seconds after the 45.54-second command. Cumulative CPU includes concurrent work and is not wall time. The main critical-path report is rooted at operation 7068; the default report also includes other outermost roots. Host I/O pressure was elevated and the capture must not replace an unprofiled benchmark.

Raw Go files are under testdata. Large text captures use gzip; archive-manifest.json verifies both original and archived hashes/sizes. Drivers contain local paths that need adaptation. No database, snapshot contents or Git metadata are included. No PR is opened.
''')
for record in records:
    saved = (dest/record['path']).read_bytes()
    assert hashlib.sha256(saved).hexdigest() == record['sha256']
    original = gzip.decompress(saved) if record['gzip'] else saved
    assert hashlib.sha256(original).hexdigest() == record['source_sha256']
print(json.dumps(dict(files=len(records), bytes=sum(r['bytes'] for r in records), verified=True)))
