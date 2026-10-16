from pathlib import Path
import gzip,hashlib,json,shutil

base=Path('/tmp/rust-cache-sipsma-review')
root=Path('hack/rust-cache/experiments/containerd-root-dedup-followup')
root.mkdir(exist_ok=False)

def copy(path,relative):
 target=root/relative
 if path.suffix in ['.go','.log','.ndjson','.txt'] or (path.name.endswith('.cache.json') and path.stat().st_size>131072):
  target=Path(str(target)+'.gz')
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('wb') as raw:
   with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as stream:stream.write(path.read_bytes())
 else:
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)

def tree(source,label):
 for path in sorted(source.rglob('*')):
  if not path.is_file():continue
  assert path.name!='containerdmeta.db'
  if path.suffix=='.test':continue
  copy(path,str(Path(label)/path.relative_to(source)))

for name in ['measure_containerd_root_dedup_carryover.py','profile_containerd_root_dedup_carryover.py',
 'measure_containerd_root_dedup_variants.py','measure_containerd_root_dedup_natural.py',
 'measure_containerd_root_dedup_single_lookup_commands.py','verify_containerd_root_dedup_single_lookup_native.py',
 'check_native_single_lookup_reuse.py','summarize_containerd_root_dedup_commands.py','local_cli_collector.py',
 'archive_containerd_root_dedup_followup.py']:
 copy(base/name,name)
copy(base/'containerd-root-dedup-followup-evidence-README.md','README.md')
for directory,label in [
 ('containerd-root-dedup-carryover','carryover'),
 ('containerd-root-dedup-allocation-profiles','allocation-profiles'),
 ('containerd-mark-graph/variants','variants'),
 ('containerd-root-dedup-single-lookup-natural','natural'),
 ('containerd-root-dedup-single-lookup-commands','concurrent'),
 ('containerd-root-dedup-single-lookup-validation','native-cold'),
 ('deep-artifact-reuse-single-lookup-oct16','native-retained')]:tree(base/directory,label)
engine=base/'containerd-root-dedup-single-lookup-engine'
for name in ['gc.go','identity.json','provenance.json','engine.go.mod','engine.go.sum','final-engine-state.json']:
 copy(engine/name,'engine/'+name)
for path in sorted(engine.glob('*.log')):copy(path,'validation/'+path.name)
tree(engine/'install','install')
copy(base/'containerd-mark-graph/progress.json','progress.json')

files=sorted(path for path in root.rglob('*') if path.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(root))+'\n' for path in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files))))
