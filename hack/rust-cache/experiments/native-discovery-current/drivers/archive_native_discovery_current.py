from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
experiment = base/'native-discovery-current'
root = Path('hack/rust-cache/experiments/native-discovery-current')
if root.exists():
    assert not (root/'SHA256SUMS').exists(), 'Refuse to overwrite a completed archive'
root.mkdir(exist_ok=True)

def copy(path, relative):
    target = root/relative
    if path.suffix in ['.go','.log','.ndjson','.txt','.trace'] or (path.name.endswith('.cache.json') and path.stat().st_size>131072):
        target = Path(str(target)+'.gz')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as raw:
            with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as output:
                output.write(path.read_bytes())
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)

def tree(source,label):
    for path in sorted(source.rglob('*')):
        if path.is_file() and '.git' not in path.relative_to(source).parts:
            assert path.suffix not in ['.test','.db']
            copy(path,str(Path(label)/path.relative_to(source)))

for name in ['measure_native_discovery_current.py',
             'measure_native_discovery_current_confirmation.py',
             'profile_native_discovery_current.py',
             'verify_native_discovery_current.py',
             'verify_native_discovery_current_drained.py',
             'verify_native_discovery_current_full.py',
             'verify_native_discovery_current_compile.py',
             'verify_native_discovery_current_compile_initial.py',
             'verify_native_discovery_current_compile_git_initial.py',
             'verify_native_discovery_current_compile_reversion_initial.py',
             'verify_native_discovery_current_compile_batch_initial.py',
             'summarize_native_discovery_current_profiles.py',
             'check_native_discovery_current_reuse.py',
             'local_cli_collector.py',
             'native_batch_runtime_inspect.go',
             'rust_packages_cache_inspect.go',
             'archive_native_discovery_current.py',
             'repro_no_git_workspace_default_path.py',
             'repro_no_git_workspace_default_path_directory.py',
             'verify_workspace_default_path_boundary.py']:
    copy(base/name,'drivers/'+name)
copy(base/'native-discovery-current-evidence-README.md','README.md')
for name in ['paired','confirmation','profiles']:
    tree(experiment/name,name)
for name in ['native-discovery-current-validation',
             'native-discovery-current-validation-drained',
             'native-discovery-current-validation-full',
             'native-discovery-current-compile-validation',
             'native-discovery-current-compile-validation-git',
             'native-discovery-current-compile-validation-confirmed',
             'native-discovery-current-compile-validation-final',
             'native-discovery-current-compile-validation-validated',
             'native-discovery-retained-oct16']:
    tree(base/name,'validation/'+name)
for name in ['native-discovery-current-validation','native-discovery-current-validation-drained','native-discovery-current-validation-full']:
    copy(base/(name+'-driver.log'),'validation/'+name+'-driver.log')
for name in ['no-git-workspace-default-path','no-git-workspace-default-path-directory']:
    tree(base/name,'validation/'+name)
for name in ['no-git-workspace-default-path-driver.log','no-git-workspace-default-path-directory-driver.log','no-git-workspace-default-path-boundary-driver.log']:
    copy(base/name,'validation/'+name)
for name in ['main.dang','dagger-module.toml']:
    copy(Path('/tmp/rust-no-git-default-path-directory-probe-module')/name,'validation/workspace-boundary-probe/'+name)
for path in sorted(experiment.iterdir()):
    if path.is_file(): copy(path,'validation/'+path.name)
for label,path in [('before',Path('/tmp/dagger-rust-native-fused-artifact-inputs')),
                   ('after',Path('/tmp/dagger-rust-native-discovery-current'))]:
    for name in ['main.dang','dagger-module.toml','compiler/go.mod','compiler/go.sum']:
        copy(path/name,'source/'+label+'/'+name)
diff = subprocess.check_output(['git','diff','3cd40e5928563ade3ea1cd21ab9924cd03d88fc3','da1ae47b6c96a3117de303b7584d028e35166530','--','main.dang'],cwd='/tmp/dagger-rust-native-discovery-current')
with (root/'source/module.patch.gz').open('wb') as raw:
    with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as output:
        output.write(diff)
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files))))
