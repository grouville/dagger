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
flags = {route: get(route)['enabled'] for route in ['batch-metadata', 'attribute-array-decode', 'gc-metadata-read-ahead', 'reusable-declarations']}
seed_mode_path = '/tmp/filesync-snapshot-seeds-mode'
seed_mode = subprocess.check_output(['docker', 'exec', record['Id'], 'cat', seed_mode_path])
orders = [['after', 'before'] if pair%2 == 0 else ['before', 'after'] for pair in range(args.pairs)]
metadata = dict(
    diagnostic='Guarded immutable Dang declarations; identical selected Go module in both arms, ordinary GC and same result cache. Existing metadata read-ahead remains off in both arms; engine cache was rebuilt after the recorded prototype crash, so earlier engine timings are not comparable.',
    collection_expansion_limit=get('collection-expansion-limit')['limit'],
    source=str(source), source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
    modules={arm: dict(path=str(path),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip(),
        hashes={name: hashlib.sha256((path/name).read_bytes()).hexdigest() for name in ['go.dang','gomod/main.dang']}) for arm,path in modules.items()},
    engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],
    pairs=args.pairs,orders=orders,wcprof=False,cpu_profiling=False,telemetry=True,ordinary_gc=True,
    fresh_edit_every_arm=True,warm_engine=True,
    warmup='Both module implementations passed focused checks; the engine has completed previous full listing cohorts. Every measured command receives a new source comment.',
    batch_metadata=True,attribute_array_decode=True,filesync_snapshot_seeds=True,metadata_read_ahead_both_arms=False,
)
assert get('collection-expansion-limit')['limit']==0
metadata['driver_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
def residency():
    return json.loads(subprocess.check_output(['docker','exec',record['Id'],'/tmp/dagger-metadata-residency'],text=True))
rows=[]
expected=None
try:
    assert not get('wcprof/enabled')['global_enabled']
    assert not get('interface-field-snapshots')['enabled']
    assert not get('collection-expansion-values')['enabled']
    for route in ['batch-metadata', 'attribute-array-decode']: mode(route,True)
    mode('gc-metadata-read-ahead',False)
    assert not get('known-input-ids')['enabled']
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    for pair,order in enumerate(orders):
        for arm in order:
            label=f'{pair}-{arm}'
            edit.write_bytes(original+f'\n// Go listing benchmark edit {time.time_ns()}\n'.encode())
            (source/'dagger.toml').write_text('[modules.go]\nsource = "'+str(modules[arm])+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
            command=[str(cli),'check','--module','go','--check','test','--list','--all']
            idle(label)
            mode('reusable-declarations', arm=='after')
            declarations_before=get('reusable-declarations')
            assert get('collection-expansion-limit?limit=0',b'')['limit']==0
            gc_before=get('snapshot-collection'); residency_before=residency()
            a=heap();ca=cpu();pa=pressure();tick=time.monotonic();wall=time.time()
            stop=threading.Event();samples=[]
            def sample():
                while not stop.wait(.25):
                    item=dict(seconds=time.monotonic()-tick,memory_current=int((cgroup/'memory.current').read_text()))
                    if not samples or item['seconds']-samples[-1].get('last_heap_at',0)>=2:
                        item['heap']=heap();item['expansion']=get('collection-expansion-limit');item['last_heap_at']=item['seconds']
                    else:item['last_heap_at']=samples[-1].get('last_heap_at',0)
                    samples.append(item)
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
            row=dict(label=label,pair=pair,arm=arm,seconds=seconds,exit_code=code,cancelled=cancelled,
                gc_before=gc_before,gc_after=get('snapshot-collection'),declarations_before=declarations_before,declarations_after=get('reusable-declarations'),residency_before=residency_before,residency_after=residency(),
                listed_rows=len(lines),same_rows=lines==expected,first_row_seconds=times[0] if times else None,
                last_row_seconds=times[-1] if times else None,engine_cpu=cb-ca,
                heap_delta={k:b[k]-a[k] for k in a},
                heap_before=a,heap_after=b,
                peak_sampled_heap=max(x['heap']['HeapAlloc'] for x in samples if 'heap' in x),
                first_nested_receiver_sample_seconds=next((x['seconds'] for x in samples if x.get('expansion',{}).get('started',0)>1),None),
                peak_sampled_memory=max(x['memory_current'] for x in samples),expansion=get('collection-expansion-limit'),
                pressure={k:(pb[k]-pa[k])/(seconds*1e6) for k in pa},unix_start=wall,unix_end=time.time())
            rows.append(row)
            (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(json.dumps(row),flush=True)
            assert len(lines)==4398 and lines==expected,(label,'listing differs',len(lines))
            assert not cancelled,(label,'timeout')
    good={arm:[r for r in rows if r['arm']==arm] for arm in modules}
    summary=dict(pairs=args.pairs,all_commands_succeeded=all(r['exit_code']==0 for r in rows),
        median_seconds={arm:statistics.median(r['seconds'] for r in rs) for arm,rs in good.items()},
        median_last_row_seconds={arm:statistics.median(r['last_row_seconds'] for r in rs) for arm,rs in good.items()},
        median_allocated_bytes={arm:statistics.median(r['heap_delta']['TotalAlloc'] for r in rs) for arm,rs in good.items()},
        median_engine_cpu={arm:statistics.median(r['engine_cpu'] for r in rs) for arm,rs in good.items()},
        faster_pairs=sum(good['after'][i]['seconds']<good['before'][i]['seconds'] for i in range(args.pairs)),
        same_rows=all(r['same_rows'] for r in rows),rows=4398)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
finally:
    edit.write_bytes(original)
    for name,data in saved.items():
        if data is None:(source/name).unlink(missing_ok=True)
        else:(source/name).write_bytes(data)
    for route,enabled in flags.items():mode(route,enabled)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=seed_mode,check=True)
