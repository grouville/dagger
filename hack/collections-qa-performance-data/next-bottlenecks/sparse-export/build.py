from pathlib import Path
import os,subprocess,json,hashlib,time
lab=Path(__file__).resolve().parent;root=Path('/home/dagger/dag')
env=dict(os.environ,GOMAXPROCS='8',CGO_ENABLED='0',GOPROXY='off')
flags=['-modfile=/tmp/collections-perf/post-rebase-io/build.mod','-buildvcs=false']
rows=[]
def run(label,cmd,environment=env,allow_failure=False):
 start=time.monotonic()
 with (lab/(label+'.log')).open('wb') as out:
  p=subprocess.run(cmd,cwd=root,env=environment,stdout=out,stderr=subprocess.STDOUT)
 row={'label':label,'command':cmd,'exit_code':p.returncode,'seconds':time.monotonic()-start};rows.append(row)
 print(json.dumps(row),flush=True)
 if not allow_failure:assert p.returncode==0,label
for variant in ['baseline','candidate']:
 run(variant+'-unit-build',['go','test','-c',*flags,'-overlay='+str(lab/(variant+'-overlay.json')),'-o',str(lab/(variant+'.test')),'./internal/fsutil'])
run('baseline-permission-regression',[str(lab/'baseline.test'),'-test.run=^TestSparseExportIndependentPermissions$','-test.v'],allow_failure=True)
run('candidate-tests',[str(lab/'candidate.test'),'-test.run=TestSparse|TestFilter','-test.v'])
run('candidate-race',['go','test','-race',*flags,'-overlay='+str(lab/'candidate-overlay.json'),'./internal/fsutil','-run=^TestSparse','-count=1'],dict(env,CGO_ENABLED='1'))
for variant in ['disk-only','key-and-disk']:
 run('cli-'+variant+'-build',['go','build',*flags,'-overlay='+str(lab/('cli-'+variant+'-overlay.json')),'-o',str(lab/('dagger-'+variant)),'./cmd/dagger'])
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
files=['diskwriter.go','diskwriter-baseline.go','artifact_list-current.go','sparse_export_test.go','sparse_export_benchmark_test.go','baseline-overlay.json','candidate-overlay.json','cli-disk-only-overlay.json','cli-key-and-disk-overlay.json','dagger-disk-only','dagger-key-and-disk','baseline.test','candidate.test']
(lab/'build-provenance.json').write_text(json.dumps({'root_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'commands':rows,'sha256':{p:sha(lab/p) for p in files}},indent=2)+'\n')
