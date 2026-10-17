from pathlib import Path
import json,os,subprocess,time,re,statistics
root=Path(__file__).parent
cwd=Path('/tmp/dagger-interface-field-snapshots-upstream')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env=dict(os.environ,GOMAXPROCS='8',CGO_ENABLED='1')
for arm in ['before','after']:
    with (root/(arm+'-benchmark-build.log')).open('w') as out:
        subprocess.run([go,'test','-p','1','-c','-overlay',str(root/(arm+'-overlay.json')),'-o',str(root/(arm+'.test')),'./dagql'],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,check=True)
    print('built',arm,flush=True)
runs=[]
for pair in range(3):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        log=root/f'benchmark-{pair}-{arm}.log'
        with log.open('w') as out:
            tick=time.monotonic()
            p=subprocess.run([str(root/(arm+'.test')),'-test.run','^TestCacheImportedDigestPostingsRemainLocalAfterMerge$','-test.bench','^BenchmarkCacheImportWideOutputClass$','-test.benchtime','1x','-test.benchmem','-test.count','1'],cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT)
        row=dict(pair=pair,arm=arm,exit_code=p.returncode,seconds=time.monotonic()-tick)
        row['benchmarks']=[]
        for line in log.read_text().splitlines():
            m=re.match(r'(Benchmark\S+)\s+(\d+)\s+([\d.]+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',line)
            if m:row['benchmarks'].append(dict(name=m[1],ns=float(m[3]),bytes=int(m[4]),allocs=int(m[5])))
        runs.append(row);(root/'benchmarks.json').write_text(json.dumps(runs,indent=2)+'\n')
        print(json.dumps(row),flush=True)
        assert p.returncode==0 and len(row['benchmarks'])==3
summary={}
for name in [r['name'] for r in runs[0]['benchmarks']]:
    summary[name]={}
    for arm in ['before','after']:
        a=[b for r in runs if r['arm']==arm for b in r['benchmarks'] if b['name']==name]
        summary[name][arm]={k:statistics.median(x[k] for x in a) for k in ['ns','bytes','allocs']}
(root/'benchmark-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2),flush=True)
