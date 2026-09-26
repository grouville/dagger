"""Sequential, source-checked builds for the matched three-engine experiment."""
from pathlib import Path
import hashlib,json,os,subprocess,time

lab=Path(__file__).resolve().parent
inputs=Path('/tmp/collections-perf/sdk-edit-audit/metadata-build-v1')
manifest=json.loads((inputs/'manifest.json').read_text())
repo=Path(manifest['repo'])
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==manifest['HEAD']
    assert not subprocess.check_output(['git','diff','--name-only'],cwd=repo,text=True).strip()
    for row in manifest['files']:assert sha(row['frozen'])==row['sha256'],row['frozen']
    for row in manifest['dangSourceState']['files']:assert sha(row['path'])==row['sha256'],row['path']
    for p,digest in manifest['versionInputs'].items():assert sha(p)==digest

env=dict(os.environ);env.update(manifest['environment'])
results={}
for variant,command in manifest['commands'].items():
    verify()
    target=Path(command[command.index('-o')+1]);assert not target.exists()
    begin=time.monotonic()
    with (lab/f'build-{variant}.log').open('wb') as log:
        subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    verify()
    results[variant]={'binary':str(target),'sha256':sha(target),'command':command,'source_HEAD':manifest['HEAD'],'build_seconds':time.monotonic()-begin}
    (lab/'builds.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results[variant]),flush=True)
