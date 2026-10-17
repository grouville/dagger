from pathlib import Path
import gzip
import hashlib
import json
import shutil

workspace = Path('/home/dagger/dagger_otra')
family = Path(__file__).parent
dest = workspace/'hack/rust-cache/experiments/dang-builtin-receivers'
previous = workspace/'hack/rust-cache/experiments/cache-usage-provider-rows'
previous_manifest = json.loads((previous/'archive-manifest.json').read_text())
by_hash = {}
for row in previous_manifest:
    by_hash.setdefault(row['source_sha256'], row)
sources = []
references = []
omissions = []

def digest(data):
    return hashlib.sha256(data).hexdigest()

def add(source, target, allow_reference=False):
    data = source.read_bytes()
    sha = digest(data)
    if allow_reference and sha in by_hash:
        row = by_hash[sha]
        references.append(dict(source=str(source), source_bytes=len(data), source_sha256=sha,
            archived='../cache-usage-provider-rows/'+row['path'], gzip=row['gzip'],
            archive_bytes=row['bytes'], archive_sha256=row['sha256']))
        return
    sources.append((source, target))

def tree(source, relative):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        if path.name == 'dagger-engine' or path.suffix == '.test':
            data = path.read_bytes()
            omissions.append(dict(source=str(path), bytes=len(data), sha256=digest(data),
                reason='Executable omitted; exact source, build command and binary identity retained.'))
            continue
        add(path, relative/path.relative_to(source))

tree(family, Path('evidence/testdata'))
candidate = Path('/tmp/dang-direct-builtin-receivers')
for name in ['pkg/dang/eval.go', 'pkg/dang/ast_expressions.go', 'pkg/dang/builtin_method.go',
             'pkg/dang/builtin_receiver_test.go', 'pkg/dang/builtin_receiver_bench_test.go']:
    add(candidate/name, Path('candidate-source/testdata')/name)
for phase, overlay_path in [('measured', family/'engine-overlay.json'),
                            ('json-compatibility', family/'json-compatibility/engine-overlay.json')]:
    overlay = json.loads(overlay_path.read_text())['Replace']
    for index, (virtual, actual) in enumerate(sorted(overlay.items())):
        add(Path(actual), Path('overlay-inputs/testdata')/phase/f'{index:03d}'/Path(actual).name,
            allow_reference=True)
engine = Path('/tmp/dagger-filesync-snapshot-seeds')
call_path = []
for name in ['core/modfunc.go', 'core/module_git_clients.go',
             'core/workspace/git_clients.go', 'core/workspace/sdk_scopes.go',
             'core/workspace/config.go', 'engine/engineutil/filesync.go',
             'engine/client/filesync.go']:
    actual = Path(overlay.get(str(engine/name), str(engine/name)))
    add(actual, Path('config-call-path/testdata')/name, allow_reference=True)
    call_path.append(dict(virtual=str(engine/name), actual=str(actual),
                          sha256=digest(actual.read_bytes())))
original = family.parent/'dang-module-blueprint-content-key'
for path in sorted(original.rglob('*')):
    if path.is_file() and '.git' not in path.parts and '__pycache__' not in path.parts:
        add(path, Path('baseline-module/testdata')/path.relative_to(original), allow_reference=True)
for name in ['engine.go.mod', 'engine.go.sum']:
    add(family.parent/'otel-evicted-queue'/name, Path('protocol/testdata')/name, allow_reference=True)
for name in ['rust-go-test-collections/measure.py', 'local_cli_collector.py',
             'restart_owned_engine_clean.py', 'glob-literal-prefix/full-command-paired/0-before.stdout']:
    add(family.parent/name, Path('protocol/testdata')/name, allow_reference=True)
for name in ['builtin-receivers-before-first', 'builtin-receivers-after-first',
             'builtin-receivers-post-cohort', 'builtin-receivers-json-before-first',
             'builtin-receivers-json-after-first']:
    path = family.parent/('native-discovery-retained-'+name)
    if path.exists():
        tree(path, Path('native-retained/testdata')/name)
module = Path('/tmp/dagger-go-module-test-name-index')
for name in ['go.dang', 'gomod/main.dang', 'dagger.toml', 'AGENTS.md']:
    add(module/name, Path('go-module/testdata')/name, allow_reference=True)
# This directory contains only this driver's generated, reproducible archive.
# Recreate it so renamed phase paths cannot leave unmanifested stale files.
if dest.exists():
    shutil.rmtree(dest)
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
(dest/'config-call-path.json').write_text(json.dumps(call_path, indent=2)+'\n')
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
print(len(manifest), 'new files and', len(references), 'inherited sources verified;',
      len(omissions), 'executables omitted.', flush=True)
