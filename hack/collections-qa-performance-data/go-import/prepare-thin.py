from pathlib import Path, PurePosixPath
import hashlib,json,tarfile,subprocess
base=Path('/tmp/collections-perf/go-import')
blobs=base/'thin-blobs';blobs.mkdir(exist_ok=True)
manifest=json.loads((base/'original-manifest.json').read_text())
config=json.loads((base/'original-config.json').read_text())
layer=manifest['layers'][2]
assert layer['digest']=='sha256:44b3c4a427a9955d872d537b7405e032d3ab6edf926a7dfc781d3126c87f97c8'
proc=subprocess.Popen(['zstd','-dc',str(base/'go-layer.zst')],stdout=subprocess.PIPE)
removed=[];kept=[]
def omit(name):
    p=PurePosixPath(name)
    if not p.is_relative_to('usr/local/go'):return False
    rel=p.relative_to('usr/local/go')
    return rel.parts[:1]==('test',) or 'testdata' in rel.parts or rel.name.endswith('_test.go')
with tarfile.open(fileobj=proc.stdout,mode='r|') as src,tarfile.open(base/'thin-layer.tar','w',format=tarfile.PAX_FORMAT) as dst:
    for m in src:
        if omit(m.name):
            removed.append({'path':m.name,'bytes':m.size});continue
        if m.islnk():assert not omit(m.linkname),m.name
        dst.addfile(m,src.extractfile(m) if m.isfile() else None)
        kept.append(m.name)
assert proc.wait()==0
subprocess.run(['zstd','-q','-f','-3',str(base/'thin-layer.tar'),'-o',str(base/'thin-layer.zst')],check=True)
def put(data):
    digest=hashlib.sha256(data).hexdigest();(blobs/digest).write_bytes(data)
    return {'digest':'sha256:'+digest,'size':len(data)}
new_layer=put((base/'thin-layer.zst').read_bytes())
manifest['layers'][2]={**layer,**new_layer}
config['rootfs']['diff_ids'][2]='sha256:'+hashlib.sha256((base/'thin-layer.tar').read_bytes()).hexdigest()
new_config=put(json.dumps(config,separators=(',',':')).encode())
manifest['config']={**manifest['config'],**new_config}
new_manifest=put(json.dumps(manifest,separators=(',',':')).encode())
meta={'sdk_manifest':new_manifest,'source_manifest':'sha256:a5a4214938de6b898267ee413c8b8f6580a08b38ac9db400742a1c934799cc70','layer':new_layer,'removed_entries':len(removed),'removed_bytes':sum(x['bytes'] for x in removed),'kept_entries':len(kept),'removed':removed}
(base/'thin-manifest.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps({k:v for k,v in meta.items() if k!='removed'},indent=2))
