"""Compile each local benchmark once, then run three alternating paired cycles."""
from pathlib import Path
import argparse,hashlib,json,os,re,statistics,subprocess,time
H=Path(__file__).resolve().parent;R=Path('/home/dagger/dag');GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--validation',type=Path,default=H/'validation-v1/results.json');p.add_argument('--out',type=Path,default=H/'benchmark-v1');a=p.parse_args()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
if not a.run:print(json.dumps({'execute':False,'cycles':3,'order':['baseline,candidate','candidate,baseline','baseline,candidate'],'bench':'^BenchmarkCoreTypeDefPublication$','benchtime':'1x','gomaxprocs':4,'scope':'first core metadata construction; excludes installed-schema/cache setup and teardown'}));raise SystemExit
assert json.loads(a.validation.read_text())['all_expected_results'];assert not a.out.exists();a.out.mkdir()
provenance=json.loads((H/'source-provenance.json').read_text());assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==provenance['head']
for path,want in provenance['source'].items():assert sha(path)==want,path
for name,want in json.loads((H/'candidate-hashes.json').read_text()).items():assert sha(H/name)==want,name
env=os.environ.copy();env.update(GOMAXPROCS='4',GOPROXY='off',GOTOOLCHAIN='local');rows=[];builds=[]
def save():(a.out/'results.json').write_text(json.dumps({'head':provenance['head'],'builds':builds,'samples':rows,'script_sha256':sha(__file__),'validation_sha256':sha(a.validation)},indent=2)+'\n')
for variant,overlay in [('baseline','baseline-consumer-overlay.json'),('candidate','test-overlay.json')]:
 binary=a.out/('test-'+variant);cmd=[GO,'test','-c','-mod=readonly','-overlay='+str(H/overlay),'-o',str(binary),'./core/schema'];started=time.monotonic()
 with(a.out/('build-'+variant+'.log')).open('w')as f:r=subprocess.run(cmd,cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=300)
 builds.append({'variant':variant,'argv':cmd,'exit_code':r.returncode,'seconds':time.monotonic()-started,'binary_sha256':sha(binary)if r.returncode==0 else None});save();assert r.returncode==0
pattern=re.compile(r'^BenchmarkCoreTypeDefPublication-\d+\s+1\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op$',re.M)
for cycle in range(3):
 for variant in (['baseline','candidate']if cycle%2==0 else ['candidate','baseline']):
  cmd=[str(a.out/('test-'+variant)),'-test.run=^$','-test.bench=^BenchmarkCoreTypeDefPublication$','-test.benchtime=1x','-test.benchmem'];started=time.monotonic()
  r=subprocess.run(cmd,cwd=R,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120);log=a.out/f'{cycle}-{variant}.txt';log.write_text(r.stdout);assert r.returncode==0,r.stdout[-1000:];match=pattern.search(r.stdout);assert match,r.stdout[-1000:]
  row={'cycle':cycle,'variant':variant,'ns_per_op':float(match[1]),'bytes_per_op':int(match[2]),'allocations_per_op':int(match[3]),'whole_process_seconds':time.monotonic()-started,'log_sha256':sha(log),'exit_code':r.returncode};rows.append(row);save();print(json.dumps(row),flush=True)
summary={v:{k:statistics.median(r[k]for r in rows if r['variant']==v)for k in ['ns_per_op','bytes_per_op','allocations_per_op']}for v in ['baseline','candidate']}
(a.out/'summary.json').write_text(json.dumps({'medians':summary,'n':3,'profile':False,'scope':'Fresh local metadata construction only; no engine/CLI wall claim'},indent=2)+'\n');print(json.dumps(summary),flush=True)
