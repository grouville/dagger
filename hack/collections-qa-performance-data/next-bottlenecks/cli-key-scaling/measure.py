from pathlib import Path
import json, os, re, statistics, subprocess

lab=Path(__file__).resolve().parent
env=dict(os.environ, GOMAXPROCS='8')
rows=[]
pattern=re.compile(r'^BenchmarkListArtifactSelectionAll/(\d+)-\d+\s+(\d+)\s+([0-9.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op$',re.M)
for pair in range(6):
    for variant in (('baseline','candidate') if pair%2==0 else ('candidate','baseline')):
        command=[str(lab/(variant+'.test')),'-test.run=^$','-test.bench=^BenchmarkListArtifactSelectionAll$','-test.benchmem','-test.benchtime=250ms','-test.count=1']
        result=subprocess.run(command,cwd='/home/dagger/dag',env=env,capture_output=True,text=True,check=True)
        (lab/f'{pair:02d}-{variant}.log').write_text(result.stdout+result.stderr)
        found=pattern.findall(result.stdout)
        assert len(found)==4,result.stdout
        for size,iters,ns,alloc,allocs in found:
            rows.append({'pair':pair,'variant':variant,'items':int(size),'iterations':int(iters),'ns_per_op':float(ns),'bytes_per_op':int(alloc),'allocs_per_op':int(allocs)})
        (lab/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(pair,variant,flush=True)
summary=[]
for size in (14,100,1000,10000):
    item={'items':size}
    for variant in ('baseline','candidate'):
        values=[r for r in rows if r['items']==size and r['variant']==variant]
        item[variant]={k:statistics.median(r[k] for r in values) for k in ('ns_per_op','bytes_per_op','allocs_per_op')}
        item[variant]['range_ns']=[min(r['ns_per_op'] for r in values),max(r['ns_per_op'] for r in values)]
    item['speedup']=item['baseline']['ns_per_op']/item['candidate']['ns_per_op']
    summary.append(item)
(lab/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
