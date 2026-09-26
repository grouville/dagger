from pathlib import Path
import subprocess,os,json,time,hashlib,re,statistics
lab=Path(__file__).resolve().parent;root=Path('/home/dagger/dag')
env=dict(os.environ,GOMAXPROCS='8',CGO_ENABLED='0',GOPROXY='off')
for variant in ['baseline','candidate']:
 cmd=['go','test','-c','-modfile=/tmp/collections-perf/post-rebase-io/build.mod','-buildvcs=false','-overlay='+str(lab/(variant+'-overlay.json')),'-o',str(lab/(variant+'-bench.test')),'./internal/fsutil']
 subprocess.run(cmd,cwd=root,env=env,check=True,stdout=subprocess.DEVNULL)
rows=[]
for index,variant in enumerate(['baseline','candidate','candidate','baseline']):
 cmd=[str(lab/(variant+'-bench.test')),'-test.run=^$','-test.bench=^BenchmarkSparse','-test.benchtime=100ms','-test.count=1']
 start=time.monotonic()
 with (lab/f'bench-{index}-{variant}.txt').open('wb') as out:subprocess.run(cmd,cwd=root,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
 data=(lab/f'bench-{index}-{variant}.txt').read_text()
 for line in data.splitlines():
  m=re.match(r'(Benchmark\S+?)-\d+\s+(\d+)\s+([0-9.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',line)
  if m:rows.append({'index':index,'variant':variant,'benchmark':m[1],'iterations':int(m[2]),'ns_per_op':float(m[3]),'bytes_per_op':int(m[4]),'allocations_per_op':int(m[5])})
 print(json.dumps({'index':index,'variant':variant,'seconds':time.monotonic()-start}),flush=True)
summary=[]
for name in sorted({r['benchmark'] for r in rows}):
 result={'benchmark':name}
 for variant in ['baseline','candidate']:
  vals=[r['ns_per_op'] for r in rows if r['variant']==variant and r['benchmark']==name]
  result[variant+'_samples_ns']=vals;result[variant+'_median_ns']=statistics.median(vals)
 result['speedup']=result['baseline_median_ns']/result['candidate_median_ns'];summary.append(result)
(lab/'benchmark-results.json').write_text(json.dumps({'rows':rows,'summary':summary,'order':['baseline','candidate','candidate','baseline'],'benchmark_source_sha256':hashlib.sha256((lab/'sparse_export_benchmark_test.go').read_bytes()).hexdigest()},indent=2)+'\n')
for r in summary:print(json.dumps(r),flush=True)
