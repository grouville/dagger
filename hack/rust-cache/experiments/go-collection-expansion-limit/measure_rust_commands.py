from pathlib import Path
import hashlib

protocol = Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
# Keep exactly the established admission checks, metrics, CLI environment and
# command timing boundaries. The fixture edits and four arms below are Rust.
exec(protocol.read_text().split('fixtures = [f for f')[0])
home = protocol.parent
selected_limit=int(os.environ.get('COLLECTION_EXPANSION_BENCH_LIMIT','32'))
fixtures = [f for f in json.loads((home/'fixtures.json').read_text())
    if f['language']=='rust' and f['packages'] in args.sizes]
modules = {'before': Path('/tmp/dagger-rust-test-collection-batched-inputs'),
    'after': Path('/tmp/dagger-rust-test-collection-batched-inputs')}
source_files = ['main.dang', 'compiler/main.go', 'compiler/test_collection.go', 'compiler/dagger.gen.go']
rng = random.Random(args.seed)
orders = {}
for fixture in fixtures:
    choices = list(itertools.permutations(['before', 'after', 'batch', 'native']))
    selected = [list(rng.choice([o for o in choices
        if (o.index('before') < o.index('after')) == (i%2==0)])) for i in range(args.pairs)]
    rng.shuffle(selected)
    orders[str(fixture['packages'])] = selected
metadata = dict(seed=args.seed, pairs=args.pairs, orders=orders,
    engine_sha256=subprocess.check_output(['docker', 'exec', record['Id'], 'sha256sum', '/usr/local/bin/dagger-engine'], text=True).split()[0],
    modules={k:dict(path=str(p), base=subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip(),
        source_sha256={f:hashlib.sha256((p/f).read_bytes()).hexdigest() for f in source_files}) for k,p in modules.items()},
    telemetry_enabled=True, wcprof=False, fresh_edit_every_arm=True, same_physical_source=True,
    ordinary_gc=True, warm_engine_and_toolchains=True, experiment='same-binary collection expansion limit 0/candidate; identical Rust module', cargo_incremental=True, cargo_workers=8,
    eight_unit_tests_per_package=True, doctests_disabled_in_fixture=True)
metadata['collection_expansion_candidate_limit']=selected_limit
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
rows = []
saved_configs = {Path(f['source'])/'dagger.toml':(Path(f['source'])/'dagger.toml').read_bytes() for f in fixtures}
saved_edits={Path(f['edit_file']):Path(f['edit_file']).read_bytes() for f in fixtures}
try:
    assert not get('wcprof/enabled')['global_enabled']
    assert not get('layercopy-known-dirs')['enabled']
    mode('batch-metadata', True)
    mode('attribute-array-decode', True)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'], input=b'on\n', check=True)
    for fixture in fixtures:
        count=fixture['packages'];source=Path(fixture['source']);config=source/'dagger.toml'
        original=saved_configs[config].decode()
        for pair in range(-1, args.pairs):
            for arm in (['before','after','batch','native'] if pair<0 else orders[str(count)][pair]):
                label=f'rust-{count}-{pair}-{arm}'
                module=modules['after' if arm=='after' else 'before']
                assert get('collection-expansion-limit?limit='+str(selected_limit if arm=='after' else 0),b'')['limit']==(selected_limit if arm=='after' else 0)
                config.write_text(re.sub(r'source = "[^"]+"','source = "'+str(module)+'"',original,count=1))
                file=Path(fixture['edit_file']);value=secrets.randbits(48)+1
                text,n=re.subn(r'pub fn edited_value\(\) -> u64 \{ \d+ \}',f'pub fn edited_value() -> u64 {{ {value} }}',file.read_text())
                assert n==1
                file.write_text(text)
                run_env=dict(env)
                if arm=='native':
                    run_env.update(RUSTC=str(rust/'rustc'),RUSTDOC=str(rust/'rustdoc'),CARGO_BUILD_JOBS='8',CARGO_INCREMENTAL='1',CARGO_TARGET_DIR=str(home/f'native-rust-{count}-target'))
                    for key in ['RUSTC_WRAPPER','RUSTC_WORKSPACE_WRAPPER','RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS']:run_env.pop(key,None)
                    command=[str(rust/'cargo'),'test','--workspace','--locked','--offline']
                elif arm=='batch':command=[str(cli),'api','call','rust','test','--source','.']
                else:command=[str(cli),'check','rust:packages/tests/test']
                idle(label)
                before_pressure=pressure();before_heap=heap();before_cpu=cpu();tick=time.monotonic();start=time.time()
                with (root/(label+'.log')).open('w') as out:
                    result=subprocess.run(command,cwd=source,env=run_env,stdout=out,stderr=subprocess.STDOUT)
                seconds=time.monotonic()-tick;after_cpu=cpu();after_heap=heap();after_pressure=pressure()
                row=dict(label=label,packages=count,pair=pair,warmup=pair<0,arm=arm,seconds=seconds,
                    exit_code=result.returncode,edit_value=value,command=command,engine_cpu=after_cpu-before_cpu,
                    expansion=get('collection-expansion-limit'),heap_delta={k:after_heap[k]-before_heap[k] for k in before_heap},
                    pressure={k:(after_pressure[k]-before_pressure[k])/(seconds*1e6) for k in before_pressure},
                    unix_start=start,unix_end=time.time())
                with (root/'attempts.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
                assert result.returncode==0,(label,result.returncode)
                if arm=='native':
                    log=(root/(label+'.log')).read_text(errors='replace')
                    assert len(re.findall(r'test result: ok\. 8 passed',log))==count,(label,'native test count')
                rows.append(row)
                (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
                print(label,round(seconds,4),'alloc',round(row['heap_delta']['TotalAlloc']/1e6),'MB',flush=True)
    summary={}
    for count in args.sizes:
        data=[r for r in rows if r['packages']==count and not r['warmup']]
        byarm={arm:[r for r in data if r['arm']==arm] for arm in ['before','after','batch','native']}
        savings=[byarm['before'][i]['seconds']-byarm['after'][i]['seconds'] for i in range(args.pairs)]
        summary[str(count)]=dict(median_seconds={arm:statistics.median(r['seconds'] for r in values) for arm,values in byarm.items()},
            median_paired_saving=statistics.median(savings),faster_pairs=sum(x>0 for x in savings),pairs=args.pairs,
            median_allocated_bytes={arm:statistics.median(r['heap_delta']['TotalAlloc'] for r in values) for arm,values in byarm.items()},
            median_engine_cpu={arm:statistics.median(r['engine_cpu'] for r in values) for arm,values in byarm.items()})
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
finally:
    for file,contents in saved_edits.items():file.write_bytes(contents)
    for config,contents in saved_configs.items():config.write_bytes(contents)
    assert get('collection-expansion-limit?limit=0',b'')['limit']==0
    mode('batch-metadata',False)
    mode('attribute-array-decode',False)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True)
