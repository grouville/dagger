from pathlib import Path
import subprocess,os,json,hashlib,time
out=Path(__file__).resolve().parent;root=Path('/home/dagger/dag')
env=dict(os.environ,GOMAXPROCS='8',GOPROXY='off',CGO_ENABLED='0')
flags=['-modfile=/tmp/collections-perf/post-rebase-io/build.mod','-buildvcs=false','-overlay='+str(out/'overlay.json')]
rows=[]
def run(label,cmd,environment=env):
 start=time.monotonic()
 with (out/(label+'.log')).open('wb') as f:p=subprocess.run(cmd,cwd=root,env=environment,stdout=f,stderr=subprocess.STDOUT)
 row={'label':label,'command':cmd,'exit_code':p.returncode,'seconds':time.monotonic()-start};rows.append(row);print(json.dumps(row),flush=True)
 assert p.returncode==0,label
run('unit',['go','test',*flags,'./internal/fsutil','-count=1','-v'])
run('race',['go','test','-race',*flags,'./internal/fsutil','-run=^TestSparse','-count=1'],dict(env,CGO_ENABLED='1'))
run('cli',['go','build',*flags,'-o',str(out/'dagger-production'),'./cmd/dagger'])
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for c in iter(lambda:f.read(1048576),b''):h.update(c)
 return h.hexdigest()
source=['diskwriter.go','diskwriter_test.go','diskwriter_benchmark_test.go','overlay.json','validate.py']
(out/'validation.json').write_text(json.dumps({'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'commands':rows,'sha256':{f:sha(out/f) for f in source+['dagger-production']},'formatter_sha256':sha(root/'internal/cmd/dagger/artifact_list.go'),'windows_native_test':'skipped on Linux; runtime Windows semantics remain unexecuted'},indent=2)+'\n')
