from pathlib import Path
import json
import os
import re
import statistics
import subprocess
import time

root=Path(__file__).parent;out=root/'components';out.mkdir(exist_ok=False)
repo=Path('/tmp/dagger-interface-field-snapshots-upstream')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
replace={}
for name in ['interfaces.go','server.go']:
    before=root/('before-'+name)
    before.write_bytes(subprocess.check_output(['git','show','HEAD:dagql/'+name],cwd=repo))
    replace[str(repo/'dagql'/name)]=str(before)
(root/'before-overlay.json').write_text(json.dumps(dict(Replace=replace),indent=2)+'\n')
for arm in ['before','after']:
    command=[go,'test','-c','-o',str(out/(arm+'.test'))]+(['-overlay',str(root/'before-overlay.json')] if arm=='before' else [])+['./dagql']
    with (out/(arm+'-build.log')).open('w') as stream:subprocess.run(command,cwd=repo,stdout=stream,stderr=subprocess.STDOUT,check=True)
def pressure():
    return {kind+'.'+line.split()[0]:int(line.split('total=')[1]) for kind in ['cpu','io','memory'] for line in Path('/proc/pressure',kind).read_text().splitlines()}
rows=[]
for pair in range(6):
    for arm in (['before','after'] if pair%2==0 else ['after','before']):
        label=f'{pair}-{arm}';before=pressure();start=time.monotonic()
        with (out/(label+'.log')).open('w') as stream:
            subprocess.run([str(out/(arm+'.test')),'-test.run=^$','-test.bench=^BenchmarkInterfaceReconciliation$','-test.benchmem','-test.benchtime=150ms','-test.count=1'],env=dict(os.environ,GOMAXPROCS='8'),stdout=stream,stderr=subprocess.STDOUT,check=True)
        seconds=time.monotonic()-start;after=pressure();metrics=[]
        for line in (out/(label+'.log')).read_text().splitlines():
            if line.startswith('Benchmark'):
                f=line.split();metrics.append(dict(name=re.sub(r'-\d+$','',f[0]),ns=float(f[2]),bytes=float(f[4]),allocations=float(f[6])))
        assert len(metrics)==4,label
        rows.append(dict(pair=pair,arm=arm,seconds=seconds,metrics=metrics,pressure={k:(after[k]-before[k])/seconds/1e6 for k in before}))
        (out/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(label,round(seconds,2),flush=True)
summary={}
for name in [m['name'] for m in rows[0]['metrics']]:
    arms={arm:[m for r in rows if r['arm']==arm for m in r['metrics'] if m['name']==name] for arm in ['before','after']}
    summary[name]={arm:{k:statistics.median(m[k] for m in ms) for k in ['ns','bytes','allocations']} for arm,ms in arms.items()}
    summary[name]['faster_pairs']=sum(a['ns']<b['ns'] for a,b in zip(arms['after'],arms['before']))
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
