from pathlib import Path
import gzip,hashlib,json
base=Path('/tmp/rust-cache-sipsma-review');repo=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments')
for family,report in [('span-resource-batches','NATIVE_SPAN_RESOURCE_BATCHES.md'),('go-cli-post-resource-profile','NATIVE_GO_CLI_PROFILE.md')]:
 source=base/family;dest=repo/family;dest.mkdir(exist_ok=False);records=[];omissions=[]
 def copy(src,target):
  data=src.read_bytes();compress=src.suffix not in ['.gz','.pprof','.go','.py','.mod','.sum','.patch','.dang'] and len(data)>4096
  if compress:target=target.with_name(target.name+'.gz')
  target.parent.mkdir(parents=True,exist_ok=True);encoded=gzip.compress(data,compresslevel=6,mtime=0) if compress else data;target.write_bytes(encoded)
  records.append(dict(path=str(target.relative_to(dest)),source=str(src),source_bytes=len(data),source_sha256=hashlib.sha256(data).hexdigest(),bytes=len(encoded),sha256=hashlib.sha256(encoded).hexdigest(),gzip=compress))
 for src in sorted(source.rglob('*')):
  if not src.is_file() or '__pycache__' in src.parts:continue
  if src.name in ['dagger-engine','wcprof-complete.ndjson']:
   omissions.append(dict(source=str(src),bytes=src.stat().st_size,sha256=hashlib.sha256(src.read_bytes()).hexdigest(),reason='Executable or merged wcprof derivation; raw chunks and source identity are retained.'));continue
  copy(src,dest/'evidence/testdata'/src.relative_to(source))
 for name in ['restart_owned_engine_clean.py','rust-go-test-collections/measure.py','interface-field-snapshots/verify_retained.py']:
  copy(base/name,dest/'protocol/testdata'/Path(name).name)
 if family=='span-resource-batches':
  overlay=json.loads((source/'engine-overlay.json').read_text())['Replace'];sources=[]
  for i,(virtual,actual) in enumerate(sorted(overlay.items())):
   src=Path(actual);target=dest/'engine-overlay/testdata'/f'{i:03d}'/src.name;copy(src,target);sources.append(dict(virtual=virtual,actual=actual,archived=str(target.relative_to(dest)),sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
  (dest/'engine-overlay-manifest.json').write_text(json.dumps(sources,indent=2)+'\n')
 else:
  (dest/'engine-source.json').write_text(json.dumps(dict(engine_sha256='cc0d943bb8b87c5e8d870b8c3c892b373a472e63d70e52c4c49100182a659dad',overlay='../span-resource-batches/engine-overlay-manifest.json',cli_sha256='e7ba08d0e40f6a46ad3eb8df7397bd6827aa348f491a9cb9a726ff705e1fb122',cli_source='../filesync-literal-walks'),indent=2)+'\n')
 for name in ['go.dang','gomod/main.dang','dagger-module.toml']:
  src=Path('/tmp/dagger-go-module-test-name-index')/name
  if src.exists():copy(src,dest/'module-source/testdata'/name)
 (dest/'archive-manifest.json').write_text(json.dumps(records,indent=2)+'\n');(dest/'omissions.json').write_text(json.dumps(omissions,indent=2)+'\n')
 (dest/'.gitattributes').write_text('# Captured source, patch context and logs retain their original bytes.\n**/testdata/** -whitespace\n')
 (dest/'README.md').write_text('# '+family+'\n\nSee [the report](../../'+report+'). Complete-command observations and limitations take precedence over component speedups. No PR is opened.\n\nRaw evidence, source variants, identities, reproduction drivers and restored state are retained. Large text captures are gzip-compressed; original and archived sizes and SHA-256s are in archive-manifest.json. Go files live under testdata to avoid introducing build packages. Executables and merged wcprof derivations are omitted with hashes; raw profiling chunks remain available. No databases, native snapshot contents or Git metadata are included. Drivers contain local absolute paths that must be adapted to reproduce elsewhere.\n')
 for record in records:
  saved=(dest/record['path']).read_bytes();assert hashlib.sha256(saved).hexdigest()==record['sha256'];decoded=gzip.decompress(saved) if record['gzip'] else saved;assert hashlib.sha256(decoded).hexdigest()==record['source_sha256']
 print(json.dumps(dict(family=family,files=len(records),bytes=sum(x['bytes'] for x in records),verified=True)),flush=True)
