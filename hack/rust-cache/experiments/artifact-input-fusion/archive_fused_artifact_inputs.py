from pathlib import Path
import gzip,hashlib,json,shutil

base=Path('/tmp/rust-cache-sipsma-review')
experiment=base/'fused-artifact-inputs'
root=Path('hack/rust-cache/experiments/artifact-input-fusion')
root.mkdir(exist_ok=False)

def copy(path,relative):
 target=root/relative
 if path.suffix in ['.go','.log','.ndjson','.txt','.trace'] or (path.name.endswith('.cache.json') and path.stat().st_size>131072):
  target=Path(str(target)+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('wb') as raw:
   with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as out:out.write(path.read_bytes())
 else:
  target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)

def tree(source,label):
 for path in sorted(source.rglob('*')):
  if path.is_file():
   assert path.suffix not in ['.test','.db']
   copy(path,str(Path(label)/path.relative_to(source)))

for name in ['profile_native_source_import.py','profile_fused_artifact_inputs.py','measure_fused_artifact_inputs.py',
 'measure_fused_artifact_inputs_confirmation.py','check_fused_artifact_input_reuse.py','verify_fused_artifact_inputs.py',
 'local_cli_collector.py','archive_fused_artifact_inputs.py']:
 copy(base/name,name)
copy(base/'artifact-input-fusion-evidence-README.md','README.md')
for name in ['paired','confirmation','profiles']:
 tree(experiment/name,name)
tree(base/'native-source-import-profiles','baseline-profiles')
tree(base/'fused-artifact-inputs-validation','native-error-repair')
tree(base/'deep-artifact-reuse-fused-inputs-oct16','native-retained-initial')
tree(base/'deep-artifact-reuse-fused-inputs-confirmed-oct16','native-retained-confirmed')
for path in sorted(experiment.iterdir()):
 if path.is_file():copy(path,'validation/'+path.name)
for label,directory in [('before',Path('/tmp/dagger-rust-native-deep-artifact-closures')),('after',Path('/tmp/dagger-rust-native-fused-artifact-inputs'))]:
 for name in ['compiler/replay/history.go','compiler/replay/batch.go','compiler/go.mod','compiler/go.sum']:
  copy(directory/name,'source/'+label+'/'+name)
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files))))
