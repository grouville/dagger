from pathlib import Path
import gzip
import hashlib
import json

base = Path('/tmp/rust-cache-sipsma-review')
source = Path(__file__).parent
dest = Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/otel-evicted-queue')
dest.mkdir(exist_ok=False)
records = []
omissions = []

def copy(src, target):
    data = src.read_bytes()
    compress = src.suffix not in ['.gz', '.pprof', '.go', '.py', '.mod', '.sum', '.patch', '.dang'] and len(data) > 4096
    if compress:
        target = target.with_name(target.name + '.gz')
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = gzip.compress(data, compresslevel=6, mtime=0) if compress else data
    target.write_bytes(encoded)
    records.append(dict(path=str(target.relative_to(dest)), source=str(src), source_bytes=len(data),
        source_sha256=hashlib.sha256(data).hexdigest(), bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(), gzip=compress))

for src in sorted(source.rglob('*')):
    if not src.is_file() or '__pycache__' in src.parts or 'sdk' in src.relative_to(source).parts:
        continue
    if src.name == 'dagger-engine':
        omissions.append(dict(source=str(src), bytes=src.stat().st_size,
            sha256=hashlib.sha256(src.read_bytes()).hexdigest(), reason='Built executable; source and build command retained.'))
        continue
    copy(src, dest / 'evidence/testdata' / src.relative_to(source))

overlay = json.loads((source / 'engine-overlay.json').read_text())['Replace']
overlay_sources = []
for i, (virtual, actual) in enumerate(sorted(overlay.items())):
    src = Path(actual)
    target = dest / 'engine-overlay/testdata' / f'{i:03d}' / src.name
    copy(src, target)
    overlay_sources.append(dict(virtual=virtual, actual=actual, archived=str(target.relative_to(dest)),
        sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
(dest / 'engine-overlay-manifest.json').write_text(json.dumps(overlay_sources, indent=2)+'\n')

original_sdk = Path('/home/dagger/go/pkg/mod/go.opentelemetry.io/otel/sdk@v1.43.0')
inventory = []
for file in sorted((source / 'sdk').rglob('*')):
    if not file.is_file():
        continue
    relative = file.relative_to(source / 'sdk')
    data = file.read_bytes()
    assert data == (original_sdk / relative).read_bytes(), relative
    inventory.append(dict(path=str(relative), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
(dest / 'sdk-source-inventory.json').write_text(json.dumps(dict(module='go.opentelemetry.io/otel/sdk@v1.43.0',
    all_files_match_original=True, files=inventory), indent=2)+'\n')
omissions.append(dict(source=str(source / 'sdk'), reason='Unmodified pinned SDK copy, identified by version, Go module checksums and verified file inventory. Modified files and virtual additions are retained separately.'))

for name in ['restart_owned_engine_clean.py', 'rust-go-test-collections/measure.py', 'interface-field-snapshots/verify_retained.py']:
    copy(base / name, dest / 'protocol/testdata' / Path(name).name)
for name in ['metadata-cpu-cumulative.txt', 'analysis.json']:
    copy(base / 'collection-item-publication' / name, dest / 'profile-context/testdata' / name)
for name in ['go.dang', 'gomod/main.dang', 'dagger-module.toml']:
    src = Path('/tmp/dagger-go-module-test-name-index') / name
    if src.exists():
        copy(src, dest / 'module-source/testdata' / name)

(dest / 'archive-manifest.json').write_text(json.dumps(records, indent=2)+'\n')
(dest / 'omissions.json').write_text(json.dumps(omissions, indent=2)+'\n')
(dest / '.gitattributes').write_text('# Preserve captured source, patch context and logs exactly.\n**/testdata/** -whitespace\n')
(dest / 'README.md').write_text('''# Telemetry queue experiment

See [the complete-command report](../../NATIVE_TELEMETRY_LINK_QUEUE.md). Component speedups are not full-command gains. No PR is opened.

The standalone patch changes OpenTelemetry's private FIFO implementation. The diagnostic setter, HTTP control and original/candidate wrapper exist only for paired experiments and are excluded from that patch. Each queue captures its mode when created, so changing the mode between complete commands does not reinterpret an existing span's storage.

Evidence includes source variants, meaningful FIFO/span/concurrency tests, original and candidate SDK checks, race results, all benchmark and listing attempts, exact source identities and restart/retention checks. Go files live under testdata. Large text captures use gzip; archive-manifest.json verifies compressed and original bytes. Drivers contain local absolute paths that need adapting elsewhere.

The SDK tree is an unmodified copy of go.opentelemetry.io/otel/sdk@v1.43.0, with version/checksums and a verified per-file inventory rather than another dependency source dump. Virtual modifications are archived. The binary is omitted with its SHA-256 and build command. No databases, native snapshot contents or Git metadata are included.

The profile context is derived from the already archived native-string-sort diagnostic, CPU windows at offsets 40.69 and 50.78 seconds. They overlap normal GC and include approximately one second after the command; cumulative CPU is not wall time. Their raw profiles remain in ../dang-native-string-sort/.
''')
for record in records:
    saved = (dest / record['path']).read_bytes()
    assert hashlib.sha256(saved).hexdigest() == record['sha256']
    decoded = gzip.decompress(saved) if record['gzip'] else saved
    assert hashlib.sha256(decoded).hexdigest() == record['source_sha256']
print(json.dumps(dict(family=dest.name, files=len(records), bytes=sum(r['bytes'] for r in records), verified=True)))
