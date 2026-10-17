from pathlib import Path
import hashlib,json,os,signal,subprocess,sys,threading,time,statistics
protocol=Path('/tmp/rust-cache-sipsma-review/rust-go-test-collections/measure.py')
exec(protocol.read_text().split('fixtures = [f for f')[0])
source=Path('/tmp/dagger-go-real-repository-main');module=Path('/tmp/dagger-go-module-test-name-index')
edit=source/'dagql/cache_test.go';original=edit.read_bytes()
saved={n:(source/n).read_bytes() if (source/n).exists() else None for n in ['dagger.toml','dagger.lock']}
routes=['batch-metadata','attribute-array-decode','gc-metadata-read-ahead','reusable-declarations','known-input-ids','callback-caller-reuse','telemetry-flush-coalescing','interface-candidate-pruning','interface-field-snapshots','collection-expansion-values']
flags={r:get(r)['enabled'] for r in routes}
seed_path='/tmp/filesync-snapshot-seeds-mode';seed=subprocess.check_output(['docker','exec',record['Id'],'cat',seed_path])
expected=[s for s in (base/'collection-expansion-values/go-listing/0-before.stdout').read_text().splitlines() if s.startswith('go ')]
meta=dict(scope='Repeated full listing after a cache reopen; every command retained. No profiling. Add a real test declaration, then remove it, using a fresh CLI each time; assert precisely one added row and its removal. Not an alternating comparison against the previous engine binary.',engine_sha256=subprocess.check_output(['docker','exec',record['Id'],'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],shared_restored_postings=get('shared-restored-postings'),source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),module_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=module,text=True).strip(),telemetry=True,normal_gc=True,forced_gc=False,flags_before=flags)
(root/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n');(root/'driver.py').write_bytes(Path(__file__).read_bytes())
rows=[]
try:
    assert not get('wcprof/enabled')['global_enabled'] and not get('snapshot-collection')['deferred']
    assert get('collection-expansion-limit')['limit']==0 and get('scalar-array-restore')['enabled']
    for r in routes:mode(r,r in ['batch-metadata','attribute-array-decode','reusable-declarations'])
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=b'on\n',check=True)
    for i in range(2):
        label=str(i);idle(label)
        marker='TestOwnershipListing'+str(time.time_ns())
        edit.write_bytes(original+(f'\nfunc {marker}(t *testing.T) {{}}\n'.encode() if i==0 else b''))
        (source/'dagger.toml').write_text('[modules.go]\nsource = "'+str(module)+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
        a=heap();ca=cpu();pa=pressure();gc=get('snapshot-collection');decl=get('reusable-declarations')
        mark=time.monotonic();wall=time.time();stop=threading.Event();samples=[]
        def sample():
            while not stop.wait(1):
                samples.append(dict(seconds=time.monotonic()-mark,heap=heap(),memory_current=int((cgroup/'memory.current').read_text())))
        sampler=threading.Thread(target=sample);sampler.start()
        try:
            with (root/(label+'.stdout')).open('w') as out,(root/(label+'.stderr')).open('w') as err:
                p=subprocess.Popen([str(cli),'check','--module','go','--check','test','--list','--all'],cwd=source,env=env,stdout=out,stderr=err,start_new_session=True)
                try:code=p.wait(timeout=300)
                except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGINT);code=p.wait();raise
        finally:stop.set();sampler.join()
        seconds=time.monotonic()-mark;b=heap();cb=cpu();pb=pressure()
        listed=[s for s in (root/(label+'.stdout')).read_text().splitlines() if s.startswith('go ')]
        row=dict(label=label,test_marker=marker,source_edit='add test' if i==0 else 'remove test',seconds=seconds,unix_start=wall,unix_end=time.time(),exit_code=code,listed_rows=len(listed),same_rows=[line for line in listed if marker not in line]==expected,engine_cpu=cb-ca,heap_before=a,heap_after=b,allocated_bytes=b['TotalAlloc']-a['TotalAlloc'],peak_sampled_heap=max([a['HeapAlloc'],b['HeapAlloc']]+[s['heap']['HeapAlloc'] for s in samples]),gc_before=gc,gc_after=get('snapshot-collection'),declarations_before=decl,declarations_after=get('reusable-declarations'),pressure={k:(pb[k]-pa[k])/(seconds*1e6) for k in pa})
        (root/(label+'-memory.json')).write_text(json.dumps(samples)+'\n');rows.append(row);(root/'runs.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps({k:row[k] for k in ['label','seconds','exit_code','listed_rows','same_rows','engine_cpu','allocated_bytes','peak_sampled_heap']}),flush=True)
        assert code==0 and [line for line in listed if marker not in line]==expected and len(listed)==(4399 if i==0 else 4398),(label,code,len(listed))
        assert sum(marker in line for line in listed)==(1 if i==0 else 0)
finally:
    edit.write_bytes(original)
    for n,data in saved.items():
        if data is None:(source/n).unlink(missing_ok=True)
        else:(source/n).write_bytes(data)
    for r,v in flags.items():mode(r,v)
    subprocess.run(['docker','exec','-i',record['Id'],'sh','-c','cat > '+seed_path],input=seed,check=True)
summary=dict(all_success=True,commands=len(rows),same_rows=True,rows=[4399,4398],metadata_edit_add_then_remove=True,median_seconds=statistics.median(r['seconds'] for r in rows),median_cpu=statistics.median(r['engine_cpu'] for r in rows),median_allocated_bytes=statistics.median(r['allocated_bytes'] for r in rows),median_peak_heap=statistics.median(r['peak_sampled_heap'] for r in rows))
(root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
