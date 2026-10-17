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
    'before': Path('/tmp/dagger-go-module-test-name-index'),
    'after': Path('/tmp/dagger-go-module-test-name-index'),
}
cli_by_arm = {arm: Path('/tmp/rust-cache-sipsma-review/filesync-literal-pathwalk/dagger-after') for arm in modules}
env['_EXPERIMENTAL_DAGGER_VERSION'] = 'v1.0.0-beta.15'
saved = {name: (source/name).read_bytes() if (source/name).exists() else None for name in ['dagger.toml', 'dagger.lock']}
edit = source/'dagql/types.go'
original = edit.read_bytes()
test_edit=source/'dagql/cache_test.go'
test_original=test_edit.read_bytes()
test_marker='TestPreparedSchemaConfirmation'+str(time.time_ns())
flags = {route: get(route)['enabled'] for route in ['batch-metadata', 'attribute-array-decode', 'gc-metadata-read-ahead', 'reusable-declarations', 'telemetry-flush-coalescing', 'callback-caller-reuse', 'lazy-type-maps', 'span-lookup-fanout', 'otel-evicted-queue', 'single-toml-parse','parallel-client-admission','restored-posting-removal','prepared-schema']}
seed_mode_path = '/tmp/filesync-snapshot-seeds-mode'
seed_mode = subprocess.check_output(['docker', 'exec', record['Id'], 'cat', seed_mode_path])
orders = [['before', 'after'] if pair%2 == 0 else ['after', 'before'] for pair in range(args.pairs)]
metadata = dict(
    diagnostic='Complete Go collection listing with an identical module and engine binary in both arms. Only the prepared-schema diagnostic flag differs. Reusable declarations and linear restored-posting deletion are enabled in both arms. Telemetry and ordinary GC remain enabled, profiling is off. One excluded initialization pair adds a real test; four measured pairs alternate and remove it. Every arm starts a new CLI and receives a fresh source edit. Correct ordered rows and successful cleanup are required; failures are retained.',
    cli_sha256=hashlib.sha256(cli_by_arm['before'].read_bytes()).hexdigest(),
    api_version=env['_EXPERIMENTAL_DAGGER_VERSION'],
    collection_expansion_limit=get('collection-expansion-limit')['limit'],
    source=str(source), source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
    modules={arm: dict(path=str(path),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip(),
        hashes={name: hashlib.sha256((path/name).read_bytes()).hexdigest() for name in ['go.dang','gomod/main.dang']}) for arm,path in modules.items()},
    engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],
    pairs=args.pairs,orders=orders,wcprof=False,cpu_profiling=False,telemetry=True,ordinary_gc=True,
    fresh_edit_every_arm=True,warm_engine=True,
    warmup='Pair 0 is retained as initial source-identity population and is excluded from all medians and paired gains. Pairs 1 through 4 alternate order. Every invocation, including warmups, starts a fresh CLI and receives a fresh source comment on the warm engine.',
    batch_metadata=True,attribute_array_decode=True,filesync_snapshot_seeds=True,metadata_read_ahead_both_arms=False,declaration_reuse_both_arms=True,
)
assert get('collection-expansion-limit')['limit']==0
metadata['driver_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
(root/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
ordinary_idle = idle
def idle(label):
    started = time.monotonic()
    while True:
        ordinary_idle(label)
        a = pressure(); mark = time.monotonic(); time.sleep(1); b = pressure()
        rate = (b['host.cpu.some']-a['host.cpu.some'])/((time.monotonic()-mark)*1e6)
        with (root/'cpu-admission.jsonl').open('a') as out:
            out.write(json.dumps(dict(label=label,host_cpu_pressure=rate,accepted=rate<.10))+'\n')
        if rate<.10: return
        assert time.monotonic()-started<180, 'host CPU admission timeout'

def residency():
    return json.loads(subprocess.check_output(['docker','exec',record['Id'],'/tmp/dagger-metadata-residency'],text=True))
rows=[]
expected=[line for line in (base/'glob-literal-prefix/full-command-paired/0-before.stdout').read_text().splitlines() if line.startswith('go ')]
pair_rows={}
try:
    assert not get('wcprof/enabled')['global_enabled']
    assert get('lock-profiler')==dict(mutex_fraction=0,block_profile_rate_ns=0)
    mode('restored-posting-removal',True)
    mode('single-toml-parse',False)
    mode('parallel-client-admission',False)
    assert not get('span-resource-batches')['enabled']
    assert not get('otel-evicted-queue')['enabled']
    assert get('shared-restored-postings')['enabled']
    assert not get('interface-candidate-pruning')['enabled']
    assert not get('interface-field-snapshots')['enabled']
    assert not get('collection-expansion-values')['enabled']
    for route in ['batch-metadata', 'attribute-array-decode']: mode(route,True)
    mode('gc-metadata-read-ahead',False)
    assert not get('known-input-ids')['enabled']
    mode('reusable-declarations',True)
    mode('lazy-type-maps',False)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    for pair,order in enumerate(orders):
        test_edit.write_bytes(test_original+(f'\nfunc {test_marker}(t *testing.T) {{}}\n'.encode() if pair==0 else b''))
        expected_count=4399 if pair==0 else 4398
        for arm in order:
            label=f'{pair}-{arm}'
            mode('prepared-schema', arm=='after')
            edit.write_bytes(original+f'\n// Go listing benchmark edit {time.time_ns()}\n'.encode())
            (source/'dagger.toml').write_text('[modules.go]\nsource = "'+str(modules[arm])+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
            command=[str(cli_by_arm[arm]),'check','--module','go','--check','test','--list','--all']
            timed_command=['/usr/bin/time','-f','{"user_seconds":%U,"system_seconds":%S,"max_rss_kib":%M}','-o',str(root/(label+'-cli-resources.json')),'--',*command]
            idle(label)
            mode('span-lookup-fanout', True)
            assert get('prepared-schema')['enabled'] == (arm=='after')
            assert get('restored-posting-removal')['enabled']
            assert not get('single-toml-parse')['enabled']
            assert not get('parallel-client-admission')['enabled']
            get('span-lookup-fanout?record=false', b'')
            assert get('lazy-type-maps')['enabled'] == False
            mode('telemetry-flush-coalescing', False)
            mode('callback-caller-reuse', False)
            declarations_before=get('reusable-declarations')
            flush_before=get('telemetry-flush-coalescing')
            callback_before=get('callback-caller-reuse')
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
                process=subprocess.Popen(timed_command,cwd=source,env=env,stdout=subprocess.PIPE,stderr=err,text=True,start_new_session=True)
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
            if pair not in pair_rows:pair_rows[pair]=lines
            correct_rows=[line for line in lines if test_marker not in line]==expected and lines==pair_rows[pair] and len(lines)==expected_count and sum(test_marker in line for line in lines)==(1 if pair==0 else 0)
            row=dict(prepared_schema=get('prepared-schema'),restored_posting_removal=get('restored-posting-removal'),parallel_client_admission=get('parallel-client-admission'),single_toml_parse=get('single-toml-parse'),queue_state=get('otel-evicted-queue'),span_lookup=get('span-lookup-fanout'),lazy_type_maps=get('lazy-type-maps')['enabled'],cli_resources=json.loads((root/(label+'-cli-resources.json')).read_text().splitlines()[-1]),label=label,pair=pair,arm=arm,seconds=seconds,exit_code=code,cancelled=cancelled,
                gc_before=gc_before,gc_after=get('snapshot-collection'),declarations_before=declarations_before,declarations_after=get('reusable-declarations'),flush_before=flush_before,flush_after=get('telemetry-flush-coalescing'),callback_before=callback_before,callback_after=get('callback-caller-reuse'),residency_before=residency_before,residency_after=residency(),
                listed_rows=len(lines),same_rows=correct_rows,test_metadata_edit='add' if pair==0 else 'remove',first_row_seconds=times[0] if times else None,
                last_row_seconds=times[-1] if times else None,engine_cpu=cb-ca,
                heap_delta={k:b[k]-a[k] for k in a},
                heap_before=a,heap_after=b,
                peak_sampled_heap=max(x['heap']['HeapAlloc'] for x in samples if 'heap' in x),
                first_nested_receiver_sample_seconds=next((x['seconds'] for x in samples if x.get('expansion',{}).get('started',0)>1),None),
                peak_sampled_memory=max(x['memory_current'] for x in samples),expansion=get('collection-expansion-limit'),
                pressure={k:(pb[k]-pa[k])/(seconds*1e6) for k in pa},unix_start=wall,unix_end=time.time())
            rows.append(row)
            (root/'samples.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(json.dumps({k:row[k] for k in ['label','seconds','exit_code','listed_rows','same_rows','engine_cpu','cli_resources']}),flush=True)
            assert correct_rows,(label,'listing differs',len(lines))
            assert not cancelled,(label,'timeout')
            # Retain cleanup failures in both arms; correctness failures still stop the cohort.
    good={arm:[r for r in rows if r['arm']==arm and r['pair']>0] for arm in modules}
    summary=dict(pairs=args.pairs-1,warmup_pairs=1,all_commands_succeeded=all(r['exit_code']==0 for r in rows),
        successful_commands={arm:sum(r['exit_code']==0 for r in rs) for arm,rs in good.items()},
        failed_commands={arm:sum(r['exit_code']!=0 for r in rs) for arm,rs in good.items()},
        median_seconds_all_attempts={arm:statistics.median(r['seconds'] for r in rs) for arm,rs in good.items()},
        successful_seconds={arm:[r['seconds'] for r in rs if r['exit_code']==0] for arm,rs in good.items()},
        median_last_row_seconds={arm:statistics.median(r['last_row_seconds'] for r in rs) for arm,rs in good.items()},
        median_allocated_bytes={arm:statistics.median(r['heap_delta']['TotalAlloc'] for r in rs) for arm,rs in good.items()},
        median_engine_cpu={arm:statistics.median(r['engine_cpu'] for r in rs) for arm,rs in good.items()},
        both_succeeded_pairs=sum(good['after'][i]['exit_code']==0 and good['before'][i]['exit_code']==0 for i in range(args.pairs-1)),
        faster_successful_pairs=sum(good['after'][i]['exit_code']==0 and good['before'][i]['exit_code']==0 and good['after'][i]['seconds']<good['before'][i]['seconds'] for i in range(args.pairs-1)),
        same_rows=all(r['same_rows'] for r in rows),rows=4398,warmup_rows=4399,metadata_edit_add_then_remove=True)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
finally:
    edit.write_bytes(original)
    test_edit.write_bytes(test_original)
    for name,data in saved.items():
        if data is None:(source/name).unlink(missing_ok=True)
        else:(source/name).write_bytes(data)
    get('span-lookup-fanout?record=false', b'')
    for route,enabled in flags.items():mode(route,enabled)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=seed_mode,check=True)
