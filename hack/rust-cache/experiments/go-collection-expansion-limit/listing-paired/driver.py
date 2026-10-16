from pathlib import Path
import hashlib
import json
import os
import signal
import statistics
import subprocess
import sys
import threading
import time

protocol = Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
exec(protocol.read_text().split('fixtures = [f for f')[0])

source = Path('/tmp/dagger-go-real-repository-main')
modules = {
    'before': Path('/tmp/dagger-go-ordered-discovery-inputs'),
    'after': Path('/tmp/dagger-go-ordered-discovery-inputs'),
}
saved = {name: (source/name).read_bytes() if (source/name).exists() else None for name in ['dagger.toml', 'dagger.lock']}
edit = source/'dagql/types.go'
original = edit.read_bytes()
flags = {route: get(route)['enabled'] for route in ['batch-metadata', 'attribute-array-decode']}
seed_mode_path = '/tmp/filesync-snapshot-seeds-mode'
seed_mode = subprocess.check_output(['docker', 'exec', record['Id'], 'cat', seed_mode_path])
limits=args.sizes
orders=[([str(n) for n in limits] if pair%2==0 else [str(n) for n in reversed(limits)]) for pair in range(args.pairs)]
skip_warmup=os.environ.get('COLLECTION_LIMIT_SKIP_WARMUP')=='1'
metadata = dict(
    source=str(source), source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
    modules={arm: dict(path=str(path),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip(),
        hashes={name: hashlib.sha256((path/name).read_bytes()).hexdigest() for name in ['go.dang','gomod/main.dang']}) for arm,path in modules.items()},
    engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],
    pairs=args.pairs,orders=orders,wcprof=False,cpu_profiling=False,telemetry=True,ordinary_gc=True,
    fresh_edit_every_arm=True,warm_engine=True,
    warmup='One complete listing with limit 0 after engine restart; its data is retained and excluded from measured summaries.',
    warmup_skipped=skip_warmup,limits=limits,diagnostic='per-parent collection expansion limit; 0 preserves unbounded behavior',
    batch_metadata=True,attribute_array_decode=True,filesync_snapshot_seeds=True,
)
metadata['driver_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
rows=[]
expected=None
original_limit=get('collection-expansion-limit')['limit']
try:
    assert not get('wcprof/enabled')['global_enabled']
    assert not get('interface-field-snapshots')['enabled']
    for route in flags: mode(route,True)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    for pair,order in ([] if skip_warmup else [(-1,['0'])])+list(enumerate(orders)):
        for arm in order:
            label=f'{pair}-limit-{arm}'
            edit.write_bytes(original+f'\n// Go listing benchmark edit {time.time_ns()}\n'.encode())
            (source/'dagger.toml').write_text('[modules.go]\nsource = "'+str(modules['before'])+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
            command=[str(cli),'check','--module','go','--check','test','--list','--all']
            idle(label)
            setting=get('collection-expansion-limit?limit='+arm,b'');assert setting['limit']==int(arm)
            a=heap();ca=cpu();pa=pressure();tick=time.monotonic();wall=time.time()
            stop=threading.Event();samples=[]
            def sample():
                while not stop.wait(.25):
                    sample=dict(seconds=time.monotonic()-tick,memory_current=int((cgroup/'memory.current').read_text()))
                    if not samples or sample['seconds']-samples[-1].get('last_heap_at',0)>=2:
                        sample['heap']=heap();sample['expansion']=get('collection-expansion-limit');sample['last_heap_at']=sample['seconds']
                    else:sample['last_heap_at']=samples[-1].get('last_heap_at',0)
                    samples.append(sample)
            sampler=threading.Thread(target=sample);sampler.start()
            times=[]
            def read_stdout(stream,output):
                for line in stream:
                    output.write(line)
                    if line.startswith('go '): times.append(time.monotonic()-tick)
            with (root/(label+'.stdout')).open('w') as out,(root/(label+'.stderr')).open('w') as err:
                process=subprocess.Popen(command,cwd=source,env=env,stdout=subprocess.PIPE,stderr=err,text=True,start_new_session=True)
                reader=threading.Thread(target=read_stdout,args=(process.stdout,out))
                reader.start()
                cancelled=False
                try:code=process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    cancelled=True;os.killpg(process.pid,signal.SIGINT);code=process.wait()
                reader.join()
            seconds=time.monotonic()-tick;stop.set();sampler.join();b=heap();cb=cpu();pb=pressure()
            (root/(label+'-memory.json')).write_text(json.dumps(samples,indent=2)+'\n')
            output=(root/(label+'.stdout')).read_text()
            lines=[line for line in output.splitlines() if line.startswith('go ')]
            if expected is None:expected=lines
            row=dict(label=label,pair=pair,warmup=pair<0,arm=arm,limit=int(arm),seconds=seconds,exit_code=code,cancelled=cancelled,
                listed_rows=len(lines),same_rows=lines==expected,first_row_seconds=times[0] if times else None,
                last_row_seconds=times[-1] if times else None,engine_cpu=cb-ca,
                heap_delta={k:b[k]-a[k] for k in a},
                first_nested_receiver_sample_seconds=next((x['seconds'] for x in samples if x.get('expansion',{}).get('started',0)>1),None),
                peak_sampled_heap=max(x['heap']['HeapAlloc'] for x in samples if 'heap' in x),
                peak_sampled_memory=max(x['memory_current'] for x in samples),
                expansion=get('collection-expansion-limit'),
                pressure={k:(pb[k]-pa[k])/(seconds*1e6) for k in pa},unix_start=wall,unix_end=time.time())
            rows.append(row)
            (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(json.dumps(row),flush=True)
            assert len(lines)==4398 and lines==expected,(label,'listing differs',len(lines))
            assert not cancelled,(label,'timeout')
    good={str(limit):[r for r in rows if r['limit']==limit and not r['warmup']] for limit in limits}
    summary=dict(pairs=args.pairs,all_commands_succeeded=all(r['exit_code']==0 for r in rows),
        median_seconds={arm:statistics.median(r['seconds'] for r in rs) for arm,rs in good.items()},
        median_allocated_bytes={arm:statistics.median(r['heap_delta']['TotalAlloc'] for r in rs) for arm,rs in good.items()},
        median_engine_cpu={arm:statistics.median(r['engine_cpu'] for r in rs) for arm,rs in good.items()},
        median_sampled_heap_peak={arm:statistics.median(r['peak_sampled_heap'] for r in rs) for arm,rs in good.items()},
        median_expansion_peak={arm:statistics.median(r['expansion']['peak'] for r in rs) for arm,rs in good.items()},
        same_rows=all(r['same_rows'] for r in rows),rows=4398)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
finally:
    edit.write_bytes(original)
    assert get('collection-expansion-limit?limit='+str(original_limit),b'')['limit']==original_limit
    for name,data in saved.items():
        if data is None:(source/name).unlink(missing_ok=True)
        else:(source/name).write_bytes(data)
    for route,enabled in flags.items():mode(route,enabled)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=seed_mode,check=True)
