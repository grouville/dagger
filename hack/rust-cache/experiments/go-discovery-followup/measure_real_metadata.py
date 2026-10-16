from pathlib import Path
import sys,hashlib,signal
protocol=Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
exec(protocol.read_text().split('fixtures = [f for f')[0])
source=Path('/tmp/dagger-go-real-repository-main')
modules={'before':Path('/tmp/dagger-go-package-test-discovery'),'after':Path('/tmp/dagger-go-ordered-discovery-inputs')}
configs={name:(source/name).read_bytes() if (source/name).exists() else None for name in ['dagger.toml','dagger.lock']}
edit=source/'core/workspace.go';original=edit.read_bytes()
metadata=dict(seed=args.seed,pairs=args.pairs,source=str(source),source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],modules={arm:dict(path=str(p),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip(),files={f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in ['go.dang','gomod/main.dang']}) for arm,p in modules.items()},fresh_edit_every_arm=True,engine_and_toolchains_warm=True,telemetry_enabled=True,wcprof=False,ordinary_gc=True,kind='Go metadata discovery; no compiler/test workloads')
rows=[];rng=random.Random(args.seed);orders={}
for kind in ['modules','files']:
    order=[['before','after'] if i%2==0 else ['after','before'] for i in range(args.pairs)];rng.shuffle(order);orders[kind]=order
metadata['orders']=orders
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
outputs={}
try:
    assert not get('wcprof/enabled')['global_enabled']
    assert not get('interface-field-snapshots')['enabled']
    for kind in ['modules','files']:
        for pair in range(-1,args.pairs):
            for arm in (['before','after'] if pair<0 else orders[kind][pair]):
                label=f'{kind}-{pair}-{arm}';module=modules[arm];value=secrets.randbits(48)+1
                edit.write_bytes(original+f'\n// Go discovery benchmark edit {value}\n'.encode())
                if kind=='files':
                    (source/'dagger.toml').write_text('[modules.gomod]\nsource = "'+str(module)+'/gomod"\n')
                    command=[str(cli),'api','call','gomod','at','--path=.','own-files','--glob=*.go']
                else:
                    (source/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
                    command=[str(cli),'api','call','go','modules','path']
                idle(label);a=heap();ca=cpu();pa=pressure();start=time.monotonic();wall=time.time()
                with (root/(label+'.stdout')).open('w') as out,(root/(label+'.stderr')).open('w') as err:
                    process=subprocess.Popen(command,cwd=source,env=env,stdout=out,stderr=err,start_new_session=True)
                    try:code=process.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGINT);code=process.wait();raise AssertionError((label,'120s timeout',code))
                seconds=time.monotonic()-start;b=heap();cb=cpu();pb=pressure()
                row=dict(kind=kind,pair=pair,warmup=pair<0,arm=arm,label=label,command=command,seconds=seconds,exit_code=code,edit=value,engine_cpu=cb-ca,heap_delta={k:b[k]-a[k] for k in a},pressure={k:(pb[k]-pa[k])/(seconds*1e6) for k in pa},unix_start=wall,unix_end=time.time())
                rows.append(row);(root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
                print(label,round(seconds,3),'alloc GB',round(row['heap_delta']['TotalAlloc']/1e9,3),flush=True)
                assert code==0,(label,code)
                text=(root/(label+'.stdout')).read_text();values=text.splitlines()
                if kind=='files':assert len(values)==2495 and values==sorted(values),(label,len(values),'file count or ordering')
                else:assert len(values)>=70 and '.' in values,(label,len(values),'module roots')
                if kind in outputs:assert text==outputs[kind],(label,'discovery outputs changed')
                else:outputs[kind]=text
    summary={}
    for kind in ['modules','files']:
        byarm={arm:[r for r in rows if r['kind']==kind and not r['warmup'] and r['arm']==arm] for arm in ['before','after']}
        savings=[byarm['before'][i]['seconds']-byarm['after'][i]['seconds'] for i in range(args.pairs)]
        summary[kind]=dict(median_seconds={a:statistics.median(r['seconds'] for r in b) for a,b in byarm.items()},median_allocated_bytes={a:statistics.median(r['heap_delta']['TotalAlloc'] for r in b) for a,b in byarm.items()},median_engine_cpu={a:statistics.median(r['engine_cpu'] for r in b) for a,b in byarm.items()},faster_pairs=sum(x>0 for x in savings),pairs=args.pairs,median_paired_saving=statistics.median(savings))
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
finally:
    edit.write_bytes(original)
    for name,contents in configs.items():
        if contents is None:(source/name).unlink(missing_ok=True)
        else:(source/name).write_bytes(contents)
