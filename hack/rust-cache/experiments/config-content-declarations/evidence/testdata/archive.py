from pathlib import Path
import gzip
import hashlib
import json

workspace = Path('/home/dagger/dagger_otra')
family = Path(__file__).parent
dest = workspace/'hack/rust-cache/experiments/config-content-declarations'
known = {}
for name in ['dang-builtin-receivers', 'cache-usage-provider-rows']:
    previous = dest.parent/name
    for row in json.loads((previous/'archive-manifest.json').read_text()):
        known.setdefault(row['source_sha256'], (name, row))
sources = []
references = []
omissions = []

def digest(data):
    return hashlib.sha256(data).hexdigest()

def add(source, target, reuse=False):
    data = source.read_bytes()
    sha = digest(data)
    if reuse and sha in known:
        name, row = known[sha]
        references.append(dict(source=str(source), source_bytes=len(data), source_sha256=sha,
            archived='../'+name+'/'+row['path'], gzip=row['gzip'],
            archive_bytes=row['bytes'], archive_sha256=row['sha256']))
    else:
        sources.append((source, target))

def tree(source, relative):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        if path.name in {'dagger-engine', 'dagql.test'} or path.suffix == '.test':
            data = path.read_bytes()
            omissions.append(dict(source=str(path), bytes=len(data), sha256=digest(data),
                reason='Executable omitted; source, build command and binary identity retained.'))
        else:
            add(path, relative/path.relative_to(source))

tree(family, Path('evidence/testdata'))
engine = Path('/tmp/dagger-filesync-snapshot-seeds')
for name in ['sdk_scopes.go', 'git_clients.go']:
    add(engine/'core/workspace'/name, Path('original-source/testdata/core/workspace')/name, reuse=True)
overlay = json.loads((family/'engine-overlay.json').read_text())['Replace']
for index, (virtual, actual) in enumerate(sorted(overlay.items())):
    add(Path(actual), Path('overlay-inputs/testdata')/f'{index:03d}'/Path(actual).name, reuse=True)
for name in ['engine.go.mod', 'engine.go.sum']:
    add(family.parent/'otel-evicted-queue'/name, Path('protocol/testdata')/name, reuse=True)
for name in ['rust-go-test-collections/measure.py', 'local_cli_collector.py',
             'restart_owned_engine_clean.py', 'glob-literal-prefix/full-command-paired/0-before.stdout']:
    add(family.parent/name, Path('protocol/testdata')/name, reuse=True)
for suffix in ['config-declarations-before-first', 'config-declarations-after-first',
               'config-declarations-post-cohort', 'config-declarations-post-capture']:
    tree(family.parent/('native-discovery-retained-'+suffix), Path('native-retained/testdata')/suffix)
module = Path('/tmp/dagger-go-module-test-name-index')
for name in ['go.dang', 'gomod/main.dang', 'dagger.toml', 'AGENTS.md']:
    add(module/name, Path('go-module/testdata')/name, reuse=True)
dest.mkdir(parents=True, exist_ok=True)
manifest = []
for source, target in sources:
    data = source.read_bytes()
    compressed = len(data)>65536 and source.suffix not in {'.gz', '.pprof'}
    if compressed:
        target = target.with_name(target.name+'.gz')
    encoded = gzip.compress(data, mtime=0) if compressed else data
    output = dest/target
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    manifest.append(dict(path=str(target), source=str(source), source_bytes=len(data),
        source_sha256=digest(data), bytes=len(encoded), sha256=digest(encoded), gzip=compressed))
(dest/'archive-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
(dest/'inherited-source-manifest.json').write_text(json.dumps(references, indent=2)+'\n')
(dest/'omitted-executables.json').write_text(json.dumps(omissions, indent=2)+'\n')
(dest/'.gitattributes').write_text('# Preserve captured source, patches and logs exactly.\n**/testdata/** -whitespace\n')
for row in manifest:
    data = (dest/row['path']).read_bytes()
    assert len(data)==row['bytes'] and digest(data)==row['sha256'], row['path']
    raw = gzip.decompress(data) if row['gzip'] else data
    assert len(raw)==row['source_bytes'] and digest(raw)==row['source_sha256'], row['path']
for row in references:
    data = (dest/row['archived']).read_bytes()
    assert len(data)==row['archive_bytes'] and digest(data)==row['archive_sha256'], row['source']
    raw = gzip.decompress(data) if row['gzip'] else data
    assert len(raw)==row['source_bytes'] and digest(raw)==row['source_sha256'], row['source']
print(len(manifest), 'captured files and', len(references), 'inherited sources verified;',
      len(omissions), 'executables omitted.', flush=True)
