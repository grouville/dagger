from pathlib import Path
import gzip,hashlib,json,shutil,subprocess

base=Path('/tmp/rust-cache-sipsma-review')
experiment=base/'telemetry-spill-batch-buffers'
root=Path('hack/rust-cache/experiments/telemetry-spill-batch-buffers')
root.mkdir(exist_ok=False)

def copy(path,relative):
    target=root/relative
    if path.suffix in ['.go','.log','.ndjson','.txt','.trace','.patch'] or path.name.endswith('.cache.json'):
        target=Path(str(target)+'.gz')
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as raw:
            with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as output:
                output.write(path.read_bytes())
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)

def tree(source,label):
    for path in sorted(source.rglob('*')):
        if not path.is_file() or '.git' in path.relative_to(source).parts:
            continue
        if path.suffix in ['.test','.db'] or path.name=='dagger-engine':
            continue
        copy(path,str(Path(label)/path.relative_to(source)))

for name in ['measure_spill_batch_buffers.py','measure_spill_batch_buffers_confirmation.py',
             'wait_then_measure_spill_buffers.py','profile_spill_batch_buffers.py',
             'check_spill_batch_buffers_reuse.py','profile_native_list_allocations.py',
             'profile_native_list_allocations_flushed.py','prepare_spill_batch_buffers_engine.py',
             'restart_owned_engine_clean.py','local_cli_collector.py',
             'native_batch_runtime_inspect.go','archive_spill_batch_buffers.py']:
    copy(base/name,'drivers/'+name)
copy(base/'spill-batch-buffers-evidence-README.md','README.md')
tree(experiment,'runs')
tree(base/'spill-batch-buffers-engine','engine')
tree(base/'spill-batch-buffers-profiles','profiles')
tree(base/'spill-buffer-retained-oct16','retained-cache')
for name in ['native-list-allocations-profiles','native-list-allocations-flushed']:
    tree(base/name,'allocation-discovery/'+name)
    copy(base/(name+'-driver.log'),'allocation-discovery/'+name+'-driver.log')
proto=base/'protobuf-field-order'
for name in ['before.go','guard.go','typed.go','small.go','measure_components.py',
             'measure_small_components.py','dependency-race.log','clientdb-race.log']:
    copy(proto/name,'unselected-protobuf/'+name)
for name in ['before-dependency.json','guard-dependency.json','typed-dependency.json','small-dependency.json','dagger.go.mod','dagger.go.sum']:
    copy(proto/name,'unselected-protobuf/'+name)
for name in ['range_bench_test.go','range_test.go']:
    copy(Path('/tmp/protobuf-field-order-experiment/internal/order')/name,'unselected-protobuf/'+name)
for name in ['component-screen','small-screen']:
    tree(proto/name,'unselected-protobuf/'+name)
candidate=Path('/tmp/dagger-telemetry-spill-batch-buffers')
for label,revision in [('before','717589c9ccacbba7d3cf902647aa5c9ca68085e8'),
                       ('after','18f246dd1842faed187bffd637a35394951e7891')]:
    for name in ['engine/clientdb/store_spill.go','engine/clientdb/store_spill_test.go']:
        content=subprocess.check_output(['git','show',revision+':'+name],cwd=candidate)
        target=root/'source'/label/(name+'.gz');target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('wb') as raw:
            with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as output:output.write(content)
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in files))))
