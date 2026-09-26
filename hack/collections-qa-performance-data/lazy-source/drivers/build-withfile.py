from pathlib import Path
import hashlib,json,os,subprocess,time
lab=Path(__file__).resolve().parent
inputs=Path('/tmp/collections-perf/sdk-edit-audit/metadata-build-v1')
candidate=inputs.parent/'withfile-source-lazy'
manifest=json.loads((inputs/'manifest.json').read_text())
repo=Path(manifest['repo'])
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==manifest['HEAD']
    assert not subprocess.check_output(['git','diff','--name-only'],cwd=repo,text=True).strip()
    for row in manifest['files']:assert sha(row['frozen'])==row['sha256'],row['frozen']
    for row in manifest['dangSourceState']['files']:assert sha(row['path'])==row['sha256'],row['path']
    for p,digest in manifest['versionInputs'].items():assert sha(p)==digest
    patch=json.loads((candidate/'manifest.json').read_text())
    for name in ('base','candidate','tests'):assert sha(patch[name]['path'])==patch[name]['sha256']
    base=json.loads((inputs/'combined-overlay.json').read_text())['Replace']
    plus=json.loads((candidate/'engine-overlay.json').read_text())['Replace']
    assert plus==dict(base,**{patch['base']['path']:patch['candidate']['path']})
verify()
target=candidate/'engine';assert not target.exists()
command=['go','build','-mod=readonly','-modfile='+str(inputs/'build.mod'),'-buildvcs=true','-overlay='+str(candidate/'engine-overlay.json'),'-o',str(target),'./cmd/engine']
env=dict(os.environ);env.update(manifest['environment'])
begin=time.monotonic()
with (lab/'build-withfile.log').open('wb') as log:
    subprocess.run(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
verify()
result={'binary':str(target),'sha256':sha(target),'command':command,'source_HEAD':manifest['HEAD'],'environment':manifest['environment'],'overlay_sha256':sha(candidate/'engine-overlay.json'),'build_seconds':time.monotonic()-begin}
(lab/'build-withfile.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
