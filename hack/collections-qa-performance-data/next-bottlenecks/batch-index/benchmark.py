from pathlib import Path
import subprocess,os,json,re,statistics,time
lab=Path('/tmp/collections-perf/warm-audit/batch-index')
env=dict(os.environ, GOMAXPROCS='8')
rows=[]
pattern=re.compile(r'^BenchmarkArtifactBatchUniqueKeys/(\d+)-\d+\s+(\d+)\s+([0-9.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op$',re.M)
for pair in range(8):
    order=['before','after'] if pair%2==0 else ['after','before']
    for label in order:
        command=[str(lab/f'core-{label}.test'),'-test.run=^$','-test.bench=^BenchmarkArtifactBatchUniqueKeys$','-test.benchmem','-test.benchtime=300ms','-test.count=1']
        start=time.monotonic()
        result=subprocess.run(command,cwd='/home/dagger/dag',env=env,capture_output=True,text=True)
        elapsed=time.monotonic()-start
        (lab/f'{pair:02d}-{label}.log').write_text(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError(f'{label} benchmark failed: {result.stderr}')
        found=pattern.findall(result.stdout)
        assert len(found)==5, result.stdout
        for size,iters,ns,nbytes,nalloc in found:
            rows.append({'pair':pair,'variant':label,'keys':int(size),'iterations':int(iters),'ns_per_op':float(ns),'bytes_per_op':int(nbytes),'allocs_per_op':int(nalloc)})
        print(f'{pair} {label}: {elapsed:.2f}s',flush=True)
        (lab/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
summary=[]
for size in (1,10,100,1000,10000):
    item={'keys':size}
    for variant in ('before','after'):
        entries=[r for r in rows if r['keys']==size and r['variant']==variant]
        item[variant]={f:statistics.median(r[f] for r in entries) for f in ('ns_per_op','bytes_per_op','allocs_per_op')}
        item[variant]['range_ns']=[min(r['ns_per_op'] for r in entries),max(r['ns_per_op'] for r in entries)]
    item['speedup']=item['before']['ns_per_op']/item['after']['ns_per_op']
    summary.append(item)
(lab/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
