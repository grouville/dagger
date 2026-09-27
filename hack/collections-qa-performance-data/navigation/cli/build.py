from pathlib import Path
import json,subprocess,os,hashlib,time,difflib
root=Path('/home/dagger/dag');out=Path('/tmp/collections-perf/cli-exit-tail-v2');m=json.loads((out/'source-manifest.json').read_text());patch=[]
for f in m['files']:
 original=Path(f['original']);before=original.read_bytes() if original.exists() else b'';after=Path(f['overlay']).read_bytes()
 assert (hashlib.sha256(before).hexdigest() if before else None)==f['baseSHA256'],f['original']
 f['candidateSHA256']=hashlib.sha256(after).hexdigest();patch.extend(difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),fromfile=str(original),tofile=f['overlay']))
(out/'source-manifest.json').write_text(json.dumps(m,indent=2)+'\n');(out/'diagnostic.patch').write_text(''.join(patch))
env=os.environ.copy();env['CGO_ENABLED']='0';env['GOMAXPROCS']='4'
r={'baseCommit':m['baseCommit'],'goVersion':subprocess.check_output(['go','version'],cwd=root,text=True).strip(),'environment':{'CGO_ENABLED':'0','GOMAXPROCS':'4'},'builds':[]}
for name,extra in [('control',[]),('diagnostic',['-overlay='+str(out/'overlay.json')])]:
 binary=out/('dagger-'+name);cmd=['go','build','-mod=readonly','-modfile='+str(out/'build.mod'),'-buildvcs=true',*extra,'-o',str(binary),'./cmd/dagger'];start=time.monotonic()
 with (out/('build-'+name+'.log')).open('w') as f:proc=subprocess.run(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT)
 item={'name':name,'command':cmd,'exitCode':proc.returncode,'seconds':time.monotonic()-start};r['builds'].append(item)
 if proc.returncode==0:item.update(binary=str(binary),sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
 (out/'build-results.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(item),flush=True)
 if proc.returncode:raise SystemExit(proc.returncode)
m['status']='both CLIs built; no runtime queries performed';(out/'source-manifest.json').write_text(json.dumps(m,indent=2)+'\n')
