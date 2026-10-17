from pathlib import Path
import gzip,hashlib,json
base=Path('/tmp/rust-cache-sipsma-review')
workspace=Path('/home/dagger/dagger_otra')
reports={
 'go-listing-lock-profile':'NATIVE_GO_LISTING_LOCKS.md',
 'session-parallel-client-init':'NATIVE_GO_LISTING_LOCKS.md',
 'go-listing-client-engine-profile':'NATIVE_GO_LISTING_CLIENT_ENGINE_PROFILE.md',
}
for name,report in reports.items():
 source=base/name
 dest=workspace/'hack/rust-cache/experiments'/name
 dest.mkdir(exist_ok=False)
 records=[];omissions=[]
 def copy(src,target):
  data=src.read_bytes()
  compress=src.suffix not in ['.gz','.pprof','.go','.py','.mod','.sum','.patch','.dang'] and len(data)>4096
  if compress:target=target.with_name(target.name+'.gz')
  target.parent.mkdir(parents=True,exist_ok=True)
  encoded=gzip.compress(data,compresslevel=6,mtime=0) if compress else data
  target.write_bytes(encoded)
  records.append(dict(path=str(target.relative_to(dest)),source=str(src),source_bytes=len(data),source_sha256=hashlib.sha256(data).hexdigest(),bytes=len(encoded),sha256=hashlib.sha256(encoded).hexdigest(),gzip=compress))
 for src in sorted(source.rglob('*')):
  if not src.is_file() or '__pycache__' in src.parts:continue
  if src.name in ['dagger-engine','wcprof-complete.ndjson']:
   omissions.append(dict(source=str(src),bytes=src.stat().st_size,sha256=hashlib.sha256(src.read_bytes()).hexdigest(),reason='Executable or merged derivation; exact build inputs and raw recorder chunks retained.'))
   continue
  copy(src,dest/'evidence/testdata'/src.relative_to(source))
 overlayfile=source/'engine-overlay.json'
 if not overlayfile.exists():overlayfile=base/'session-parallel-client-init/engine-overlay.json'
 overlay=json.loads(overlayfile.read_text())['Replace'];manifest=[]
 for index,(virtual,actual) in enumerate(sorted(overlay.items())):
  target=dest/'engine-overlay/testdata'/f'{index:03d}'/Path(actual).name
  copy(Path(actual),target)
  manifest.append(dict(virtual=virtual,actual=actual,archived=str(target.relative_to(dest)),sha256=hashlib.sha256(Path(actual).read_bytes()).hexdigest()))
 (dest/'engine-overlay-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 for path in ['restart_owned_engine_clean.py','rust-go-test-collections/measure.py','interface-field-snapshots/verify_retained.py','otel-evicted-queue/engine.go.mod','otel-evicted-queue/engine.go.sum']:
  src=base/path
  if src.exists():copy(src,dest/'protocol/testdata'/Path(path).name)
 copy(Path(__file__),dest/'protocol/testdata'/Path(__file__).name)
 for path in ['go.dang','gomod/main.dang','AGENTS.md']:
  src=Path('/tmp/dagger-go-module-test-name-index')/path
  copy(src,dest/'module-source/testdata'/path)
 for path in ['engine/server/client_scope.go','core/schema/coremod.go']:
  src=Path('/tmp/dagger-filesync-snapshot-seeds')/path
  copy(src,dest/'reference/testdata'/path)
 if name=='go-listing-client-engine-profile':
  p=base/'filesync-literal-pathwalk/cli-after-overlay.json'
  copy(p,dest/'cli-overlay/testdata'/p.name)
  cli_manifest=[]
  for index,(virtual,actual) in enumerate(sorted(json.loads(p.read_text())['Replace'].items())):
   target=dest/'cli-overlay/testdata'/f'{index:03d}'/Path(actual).name
   copy(Path(actual),target)
   cli_manifest.append(dict(virtual=virtual,actual=actual,archived=str(target.relative_to(dest)),sha256=hashlib.sha256(Path(actual).read_bytes()).hexdigest()))
  (dest/'cli-overlay-manifest.json').write_text(json.dumps(cli_manifest,indent=2)+'\n')
  copy(base/'session-parallel-client-init/controlled-checks.json',dest/'engine-build/testdata/controlled-checks.json')
 (dest/'archive-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
 (dest/'omissions.json').write_text(json.dumps(omissions,indent=2)+'\n')
 (dest/'.gitattributes').write_text('# Preserve captured source, patches and logs exactly.\n**/testdata/** -whitespace\n')
 intro={'go-listing-lock-profile':'Sampled mutex/block waits and wcprof from the original admission policy. This is diagnostic evidence, not a performance improvement.',
        'session-parallel-client-init':'The concurrent-admission candidate remains disabled after four full listing pairs fail to establish a useful gain. Every command, test, raw standalone patch and source identity is retained.',
        'go-listing-client-engine-profile':'One full listing with both CLI and engine CPU/allocation captures and complete engine wcprof. Profiled duration is not a latency benchmark; the expected incomplete CLI tail is retained.'}[name]
 (dest/'README.md').write_text(f'# {name}\n\n{intro} See [the report](../../{report}). No PR is opened.\n\nThe manifest verifies source and archived bytes. Large text captures use gzip. Raw Go source lives under testdata. Executables and merged recorder derivations are omitted with hashes; build inputs, profile windows and raw recorder chunks remain available. No database, snapshot contents or Git metadata are included. The pinned telemetry SDK/module copies are identified by ../otel-evicted-queue/. Drivers contain local paths requiring adaptation.\n')
 for row in records:
  saved=(dest/row['path']).read_bytes()
  assert hashlib.sha256(saved).hexdigest()==row['sha256']
  decoded=gzip.decompress(saved) if row['gzip'] else saved
  assert hashlib.sha256(decoded).hexdigest()==row['source_sha256']
 print(json.dumps(dict(family=name,files=len(records),bytes=sum(r['bytes'] for r in records),verified=True)),flush=True)
