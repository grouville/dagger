from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
repo = Path('/home/dagger/dagger_otra')
archives = repo / 'hack/rust-cache/experiments'
records = []


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def copy(source, destination):
    source = Path(source)
    # Source snapshots must not become packages in the enclosing Go module.
    if source.suffix == '.go':
        relative = destination.relative_to(archives)
        if relative.parts[1] != 'testdata':
            destination = archives / relative.parts[0] / 'testdata' / Path(*relative.parts[1:])
    compress = source.suffix in {'.log', '.ndjson', '.pprof', '.stderr', '.stdout'} or (
        source.suffix == '.txt' and source.stat().st_size > 32768)
    if compress:
        destination = Path(str(destination) + '.gz')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        with source.open('rb') as src, destination.open('wb') as out:
            with gzip.GzipFile(filename='', mode='wb', fileobj=out, mtime=0) as target:
                shutil.copyfileobj(src, target)
    else:
        shutil.copyfile(source, destination)
    records.append(dict(source=str(source), destination=str(destination.relative_to(archives)),
        source_bytes=source.stat().st_size, source_sha256=digest(source),
        archived_bytes=destination.stat().st_size, archived_sha256=digest(destination), gzip=compress))
    return destination


def tree(source, destination):
    for p in sorted(source.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.name in {'dagger-engine', 'archive.log'}:
            continue
        if p.suffix == '.test' or (p.stat().st_mode & 0o111 and p.suffix not in {'.py', '.sh'}):
            continue
        relative = p.relative_to(source)
        if source.name == 'interface-field-snapshots' and relative == Path('manifest.json'):
            relative = Path('build-source-manifest.json')
        copy(p, destination / relative)


interface = archives / 'interface-field-snapshots'
tree(base / 'interface-field-snapshots', interface)
probe = base / 'function-call-argument-fields'
if probe.exists():
    tree(probe, interface / 'argument-fields-probe')
for arm in ['before', 'after']:
    tree(base / f'native-discovery-retained-interface-snapshots-{arm}-v2',
        interface / 'retained' / arm)

manifest = json.loads((base / 'interface-field-snapshots/manifest.json').read_text())
overlay_sources = []
for original, record in manifest.items():
    path = Path(record['replacement'])
    assert digest(path) == record['sha256'], original
    try:
        relative = Path(original).relative_to('/tmp/dagger-filesync-snapshot-seeds')
    except ValueError:
        relative = Path('external') / original.lstrip('/')
    destination = interface / 'engine-source' / relative
    destination = copy(path, destination)
    overlay_sources.append(dict(original=original, archived=str(destination.relative_to(archives)), sha256=digest(path)))
(interface / 'engine-source').mkdir(parents=True, exist_ok=True)
(interface / 'engine-source/overlays.json').write_text(json.dumps(overlay_sources, indent=2) + '\n')
candidate = Path('/tmp/dagger-interface-field-snapshots-upstream')
for rel in ['dagql/interfaces.go', 'dagql/server.go', 'dagql/interface_reconciliation_benchmark_test.go']:
    copy(candidate / rel, interface / 'upstream-source' / rel)
patch = subprocess.check_output(['git', 'diff', '--', 'dagql/interfaces.go', 'dagql/server.go'], cwd=candidate)
(interface / 'upstream-source').mkdir(parents=True, exist_ok=True)
(interface / 'upstream-source/production.patch').write_bytes(patch)

go = archives / 'go-discovery-followup'
tree(base / 'go-discovery-followup', go)
for name in ['clean-main-refined-module', 'clean-main-ordered-inputs',
        'clean-main-ordered-existence', 'clean-main-final-discovery']:
    source = base / 'rust-go-test-collections' / ('real-go-discovery-' + name)
    if source.exists():
        tree(source, go / 'real-repository' / name)
for name in ['profile_real_go_active.py', 'measure.py', 'fixtures.json', 'many-file-fixture.json']:
    copy(base / 'rust-go-test-collections' / name, go / 'protocol' / name)
for arm, source in [('before', Path('/tmp/dagger-go-package-test-discovery')),
        ('after', Path('/tmp/dagger-go-ordered-discovery-inputs'))]:
    for rel in ['go.dang', 'gomod/main.dang', 'AGENTS.md', 'dagger-module.toml',
            'gomod/dagger-module.toml', '.dagger/modules/go-dev/main.dang',
            'gomod/.dagger/modules/e2e/main.dang']:
        copy(source / rel, go / 'module-source' / arm / rel)

for directory in [interface, go]:
    own = [r for r in records if r['destination'].startswith(directory.name + '/')]
    (directory / 'manifest.json').write_text(json.dumps(own, indent=2) + '\n')
    for r in own:
        assert digest(archives / r['destination']) == r['archived_sha256']
    print(directory.name, len(own), sum(r['archived_bytes'] for r in own), 'bytes', flush=True)
