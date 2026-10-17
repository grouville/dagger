from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).parent/'dependency-provenance';root.mkdir(exist_ok=True)
modules={
'dang':Path('/tmp/rust-cache-sipsma-review/dang-module-blueprint-content-key'),
'containerd':Path('/tmp/containerd-gc-source'),
'otel-sdk':Path('/tmp/rust-cache-sipsma-review/otel-evicted-queue/sdk')}
for name,source in modules.items():
    target=root/name;target.mkdir(exist_ok=True)
    manifest=[]
    for path in sorted(source.rglob('*.go')):
        if '.git' in path.parts:continue
        data=path.read_bytes();manifest.append(dict(path=str(path.relative_to(source)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    p=subprocess.run(['git','-C',str(source),'rev-parse','--show-toplevel'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    metadata=dict(source=str(source),go_files=manifest)
    if p.returncode==0:
        repository=Path(p.stdout.strip());prefix=source.relative_to(repository)
        metadata.update(repository=str(repository),module_subdirectory=str(prefix),commit=subprocess.check_output(['git','-C',str(repository),'rev-parse','HEAD'],text=True).strip())
        patch=subprocess.check_output(['git','-C',str(repository),'diff','--binary','HEAD','--',str(prefix)])
        (target/'working-tree.patch').write_bytes(patch)
        untracked=subprocess.check_output(['git','-C',str(repository),'ls-files','--others','--exclude-standard','--',str(prefix)],text=True).splitlines()
        for relative in untracked:
            path=repository/relative
            if path.is_file() and (path.suffix in {'.go','.c','.h','.s'} or path.name in {'go.mod','go.sum'}):
                out=target/'untracked-source'/path.relative_to(source);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(path.read_bytes())
    else:
        # This SDK is a source copy rather than a checkout. Preserve its source.
        for path in sorted(source.rglob('*')):
            if path.is_file() and (path.suffix in {'.go','.c','.h','.s'} or path.name in {'go.mod','go.sum','LICENSE'}):
                out=target/'source'/path.relative_to(source);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(path.read_bytes())
    (target/'identity.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(name,len(manifest),'Go source files identified',flush=True)
