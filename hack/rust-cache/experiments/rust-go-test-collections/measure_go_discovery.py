from pathlib import Path

# Reuse the timing protocol, counters and CLI environment of the granularity
# comparison; execute only its setup, before any fixture loop or mutations.
exec((Path(__file__).parent/'measure.py').read_text().split('fixtures = [f for f')[0])
fixtures=[f for f in json.loads((home/'fixtures.json').read_text()) if f['language']=='go' and f['packages'] in args.sizes]
modules={'before':Path('/tmp/dagger-go-official-collections-oct16'),'after':Path('/tmp/dagger-go-package-test-discovery')}
rng=random.Random(args.seed);orders={}
for fixture in fixtures:
    choices=list(itertools.permutations(['before','after','batch','native']))
    selected=[list(rng.choice([o for o in choices if (o.index('before')<o.index('after'))==(i%2==0)])) for i in range(args.pairs)]
    rng.shuffle(selected);orders[str(fixture['packages'])]=selected
metadata=dict(seed=args.seed,pairs=args.pairs,orders=orders,engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],modules={k:dict(path=str(p),base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip(),go_dang_sha256=__import__('hashlib').sha256((p/'go.dang').read_bytes()).hexdigest()) for k,p in modules.items()},telemetry_enabled=True,wcprof=False,fresh_edit_every_arm=True,same_physical_source=True,ordinary_gc=True)
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
rows=[]
try:
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    for fixture in fixtures:
        count=fixture['packages'];source=Path(fixture['source']);original=(source/'dagger.toml').read_text()
        for pair in range(-1,args.pairs):
            for arm in (['before','after','batch','native'] if pair<0 else orders[str(count)][pair]):
                label=f'go-{count}-{pair}-{arm}';module=modules['after' if arm=='after' else 'before']
                (source/'dagger.toml').write_text(re.sub(r'source = "[^"]+"','source = "'+str(module)+'"',original,count=1))
                file=Path(fixture['edit_file']);value=secrets.randbits(48)+1
                text,n=re.subn(r'func EditedValue\(\) uint64 \{ return \d+ \}',f'func EditedValue() uint64 {{ return {value} }}',file.read_text());assert n==1;file.write_text(text)
                run_env=dict(env)
                if arm=='native':
                    run_env.update(CGO_ENABLED='0',GOMAXPROCS='8',GOCACHE=str(home/'native-go-cache'));command=[str(go),'test','-p=8','./...']
                elif arm=='batch':command=[str(cli),'api','call','go','module','--path=.','test']
                else:command=[str(cli),'check','go:packages/tests/test']
                idle(label);before_pressure=pressure();before_heap=heap();before_cpu=cpu();tick=time.monotonic();start=time.time()
                with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,cwd=source,env=run_env,stdout=out,stderr=subprocess.STDOUT)
                seconds=time.monotonic()-tick;after_heap=heap();after_cpu=cpu();after_pressure=pressure()
                row=dict(label=label,packages=count,pair=pair,warmup=pair<0,arm=arm,seconds=seconds,exit_code=r.returncode,edit_value=value,command=command,engine_cpu=after_cpu-before_cpu,heap_delta={k:after_heap[k]-before_heap[k] for k in before_heap},pressure={k:(after_pressure[k]-before_pressure[k])/(seconds*1e6) for k in before_pressure},unix_start=start,unix_end=time.time())
                with (root/'attempts.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
                assert r.returncode==0,(label,r.returncode)
                log=(root/(label+'.log')).read_text(errors='replace')
                if arm=='native':assert len(re.findall(r'^ok\s+example.com/testcollections/',log,re.M))==count,label
                rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,round(seconds,4),'alloc',round(row['heap_delta']['TotalAlloc']/1e6),'MB',flush=True)
        (source/'dagger.toml').write_text(original)
    summary={}
    for count in args.sizes:
        data=[r for r in rows if r['packages']==count and not r['warmup']];byarm={arm:[r for r in data if r['arm']==arm] for arm in ['before','after','batch','native']}
        savings=[byarm['before'][i]['seconds']-byarm['after'][i]['seconds'] for i in range(args.pairs)]
        summary[str(count)]=dict(median_seconds={arm:statistics.median(r['seconds'] for r in values) for arm,values in byarm.items()},median_paired_saving=statistics.median(savings),faster_pairs=sum(x>0 for x in savings),pairs=args.pairs,median_allocated_bytes={arm:statistics.median(r['heap_delta']['TotalAlloc'] for r in values) for arm,values in byarm.items()},median_engine_cpu={arm:statistics.median(r['engine_cpu'] for r in values) for arm,values in byarm.items()})
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
finally:
    mode('batch-metadata',False);mode('attribute-array-decode',False)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True)
