from pathlib import Path
import gzip,hashlib,json,shutil
src=Path(__file__).parent
out=Path('/home/dagger/dagger_otra/hack/rust-cache/experiments/go-dang-reusable-declarations')
out.mkdir(parents=True,exist_ok=True)
# Preserve small source/results, including rejected attempts; omit binaries,
# raw event streams and database files.
for path in src.rglob('*'):
 if not path.is_file():continue
 if path.suffix in {'.db','.test','.pprof'} or path.name.startswith('dagger-engine'):continue
 if path.suffix=='.ndjson':continue
 if path.suffix not in {'.go','.py','.json','.jsonl','.log','.txt','.mod','.sum','.stderr','.stdout','.gz'} and '.attempt-' not in path.name:continue
 dest=out/'evidence'/path.relative_to(src);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
for path in (src/'profile-declarations').glob('*.pprof'):
 dest=out/'evidence/profile-declarations'/path.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
for name in ['full-command-pilot','full-command-reverse','known-input-full-pilot']:
 path=out/'evidence'/name/'samples.json'
 if path.exists():assert all(x['exit_code']==0 and x['listed_rows']==4398 for x in json.loads(path.read_text()))
replacements=json.loads((src/'test-overlay.json').read_text())['Replace']
manifest={}
for index,(virtual,path) in enumerate(replacements.items()):
 data=Path(path).read_bytes();digest=hashlib.sha256(data).hexdigest()
 dest=out/'sources'/f'{index:02d}-{Path(virtual).name}'
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
 manifest[virtual]={'source':str(dest.relative_to(out)),'sha256':digest,'original_replacement':path}
# Record changes to local replacement modules against their pinned versions.
for label,current,original in [
 ('dang',Path('/tmp/rust-cache-sipsma-review/dang-module-blueprint-content-key'),Path('/home/dagger/go/pkg/mod/github.com/vito/dang/v2@v2.1.4')),
 ('containerd',Path('/tmp/containerd-gc-source'),Path('/home/dagger/go/pkg/mod/github.com/containerd/containerd/v2@v2.2.5'))]:
 if not original.is_dir():raise RuntimeError('Missing module baseline: '+str(original))
 for path in current.rglob('*.go'):
  relative=path.relative_to(current);base=original/relative;data=path.read_bytes()
  if base.exists() and base.read_bytes()==data:continue
  dest=out/'module-deltas'/label/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
  manifest[str(path)]={'source':str(dest.relative_to(out)),'sha256':hashlib.sha256(data).hexdigest(),'baseline':str(base)}
(out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for relative in ['go.dang','gomod/main.dang','.dagger/modules/go-dev/main.dang']:
 data=(Path('/tmp/dagger-go-ordered-discovery-inputs')/relative).read_bytes()
 dest=out/'go-module'/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
old=Path('/tmp/rust-cache-sipsma-review/go-native-module-lookup/full-command-pilot')
for path in old.glob('*'):
 if path.is_file() and path.suffix in {'.json','.jsonl','.py','.stdout','.stderr'}:
  dest=out/'ownership-inline-control'/path.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
(out/'README.md').write_text('''# Go listing: prepared declarations

See [the report](../../NATIVE_DANG_REUSABLE_DECLARATIONS.md). This is an opt-in prototype, not an upstream PR. The selected Go implementation is unchanged.

`source-manifest.json` identifies the exact overlay files. Engine base: `19eda924854e7f22582f3a7430272aa729cbeb5f`; Go module: `b5dd9434a52972787171a016a8aa9d8910c17c38`; repository fixture: `ff0b029a4d270a651b9a8c7286babc79089066e4`. Absolute paths in the original drivers identify the diagnostic environment and must be mapped when reproducing elsewhere. The module delta directories preserve changes against Dang v2.1.4 and containerd v2.2.5; the engine modfile records exact replacements.

`full-command-pilot` and `full-command-reverse` contain opposite run orders, fresh edits, all rows, engine GC events, heap samples and exit status. `known-input-full-pilot` tests the independent ID shortcut with declaration reuse off. Profiling is diagnostic and excluded from clean latency results.

The first recipe-only ID prototype panicked; engine recovery deliberately cold-started its query cache. Its errors and the native history restoration are retained. Successful comparisons use a new baseline on that recovered engine. They cannot establish a speedup against the earlier engine cache state. All six native Rust histories were subsequently restored and verified, then preserved across a graceful engine replacement.

No engine binaries, database files or private metadata database copies are included. Both experimental modes are restored off after each driver.
''')
print(json.dumps({'files':sum(p.is_file() for p in out.rglob('*')),'bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),'output':str(out)}))
