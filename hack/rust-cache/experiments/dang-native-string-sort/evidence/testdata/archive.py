from pathlib import Path
import gzip,hashlib,json
source=Path(__file__).parent
destination=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/dang-native-string-sort')
destination.mkdir(exist_ok=False)
records=[];omissions=[]
def copy(src,target):
 data=src.read_bytes()
 compress=src.suffix not in ['.gz','.pprof','.go','.py','.mod','.sum','.patch','.dang'] and len(data)>4096
 if compress:target=target.with_name(target.name+'.gz')
 target.parent.mkdir(parents=True,exist_ok=True)
 encoded=gzip.compress(data,compresslevel=6,mtime=0) if compress else data
 target.write_bytes(encoded)
 records.append(dict(path=str(target.relative_to(destination)),source=str(src),source_bytes=len(data),source_sha256=hashlib.sha256(data).hexdigest(),bytes=len(encoded),sha256=hashlib.sha256(encoded).hexdigest(),gzip=compress))
for src in sorted(source.rglob('*')):
 if not src.is_file() or '__pycache__' in src.parts:continue
 if src.name in ['dagger-engine','wcprof-complete.ndjson']:
  omissions.append(dict(source=str(src),bytes=src.stat().st_size,sha256=hashlib.sha256(src.read_bytes()).hexdigest(),reason='Executable or merged wcprof derivation. Exact source/identity and raw gzip chunks are retained.'))
  continue
 copy(src,destination/'evidence/testdata'/src.relative_to(source))
overlay=json.loads((source/'engine-overlay.json').read_text())['Replace']
source_manifest=[]
for i,(virtual,actual) in enumerate(sorted(overlay.items())):
 src=Path(actual);target=destination/'engine-overlay/testdata'/f'{i:03d}'/src.name
 copy(src,target);source_manifest.append(dict(virtual=virtual,actual=actual,archived=str(target.relative_to(destination)),sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
(destination/'engine-overlay-manifest.json').write_text(json.dumps(source_manifest,indent=2)+'\n')
for arm,path in [('before',Path('/tmp/dagger-go-module-test-name-index')),('after',Path('/tmp/dagger-go-native-string-sort'))]:
 for src in sorted(path.rglob('*')):
  if not src.is_file() or '.git' in src.parts:continue
  if src.suffix in ['.dang','.toml','.lock'] or src.name in ['EXPERIMENT_NATIVE_SORT.md','AGENTS.md']:
   copy(src,destination/'module-source'/arm/'testdata'/src.relative_to(path))
(destination/'omissions.json').write_text(json.dumps(omissions,indent=2)+'\n')
(destination/'archive-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
for record in records:
 saved=(destination/record['path']).read_bytes()
 assert hashlib.sha256(saved).hexdigest()==record['sha256']
 decoded=gzip.decompress(saved) if record['gzip'] else saved
 assert hashlib.sha256(decoded).hexdigest()==record['source_sha256']
(destination/'README.md').write_text("""# Native string sorting: complete Go listing experiment

See [the report](../../NATIVE_DANG_STRING_SORT.md). Four measured pairs return the same 4,398 rows and exit successfully. Medians are 48.06 → 45.98 seconds; three pairs improve and one regresses. The candidate remains unselected and requires a provisional Dang builtin unavailable on stock beta.15.

The archive includes both module variants, the typed native implementation and tests, pure library test overlays, the complete controlled-engine overlay inventory, every timing attempt, profile chunks, CPU/allocation captures, source identities and native-cache retention checks. Go files are below testdata to avoid introducing build packages.

The profile captures are diagnostics, excluded from timing claims. Their CPU windows extend into maintenance after command completion. pprof's source-line display must use the compiled overlay: the absolute checkout may differ. In particular, clientSpans.ExportSpans line 938 is the resource encoder in engine-overlay-manifest.json's telemetry.go replacement.

Large text evidence is gzip-compressed with original sizes and SHA-256s in archive-manifest.json. The merged wcprof file is reconstructible from the raw chunks; it and the engine executable are omitted with hashes. No databases, snapshots, credentials, targets or Git metadata are included. Drivers describe local absolute paths that must be adapted to reproduce elsewhere. No PR is opened.
""")
print(json.dumps(dict(destination=str(destination),files=len(records),bytes=sum(x['bytes'] for x in records),verified=True)))
