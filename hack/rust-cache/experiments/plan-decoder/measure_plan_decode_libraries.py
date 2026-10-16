from pathlib import Path
import hashlib,json,os,statistics,subprocess,time
base=Path('/tmp/rust-cache-sipsma-review')
root=base/'plan-decode-libraries'
output=root/'first-use'
output.mkdir(exist_ok=False)
plans={name:base/f'deep-artifact-reuse-usage-maps-post-restart/{name}-before.cache.json.plan.json' for name in ['130','1026','small']}
env=dict(os.environ,GOMAXPROCS='8')
orders=[['standard','goccy','segmentio'],['segmentio','goccy','standard'],['goccy','standard','segmentio'],['standard','segmentio','goccy'],['segmentio','standard','goccy'],['goccy','segmentio','standard']]
def pressure():
    return {kind:int(Path('/proc/pressure/'+kind).read_text().splitlines()[0].split('total=')[1]) for kind in ['cpu','io','memory']}
def admit(label):
    start=time.monotonic()
    while True:
        before=pressure();t=time.monotonic();time.sleep(1);after=pressure();seconds=time.monotonic()-t
        ratios={k:(after[k]-before[k])/(seconds*1e6) for k in before}
        admitted=ratios['io']<.05 and ratios['cpu']<.10
        with (output/'admission.jsonl').open('a') as f:f.write(json.dumps(dict(label=label,seconds=time.monotonic()-start,pressure=ratios,admitted=admitted))+'\n')
        if admitted:return
        assert time.monotonic()-start<60,'quiet admission timeout'
rows=[]
for pair in range(6):
    for size,path in plans.items():
        for decoder in orders[pair]:
            label=f'{pair}-{size}-{decoder}';admit(label)
            before=pressure();start=time.monotonic()
            completed=subprocess.run([str(root/'benchmark'),'-mode',decoder,'-plan',str(path)],env=env,text=True,capture_output=True)
            seconds=time.monotonic()-start;after=pressure()
            (output/(label+'.log')).write_text(completed.stdout+completed.stderr)
            assert completed.returncode==0,label
            result=json.loads(completed.stdout)
            row=dict(pair=pair,size=size,process_seconds=seconds,**result,pressure={k:(after[k]-before[k])/(seconds*1e6) for k in before})
            rows.append(row);(output/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(pair,size,{r['decoder']:round(r['seconds']*1000,2) for r in rows if r['pair']==pair and r['size']==size},flush=True)
summary={}
for size in plans:
    summary[size]={}
    assert len({r['canonical_sha256'] for r in rows if r['size']==size})==1
    for decoder in orders[0]:
        group=[r for r in rows if r['size']==size and r['decoder']==decoder]
        summary[size][decoder]={key:statistics.median(r[key] for r in group) for key in ['seconds','process_seconds','allocated_bytes','allocations']}
        summary[size][decoder]['gc_cycles']=sum(r['go_gc_cycles'] for r in group)
(output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(output/'source-hashes.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'main.go',root/'go.mod',root/'go.sum',root/'model/model.go',*plans.values()]},indent=2)+'\n')
print(json.dumps(summary),flush=True)
