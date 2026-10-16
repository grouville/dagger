from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import gzip,json,os,re,secrets,subprocess,time,urllib.request
base=Path('/tmp/rust-cache-sipsma-review')
root=base/'plan-decoder-command-profiles'
root.mkdir(exist_ok=False)
source=Path('/tmp/rust-native-config-entry-1026-before')
config=source/'dagger.toml';original=config.read_text()
modules={'before':'/tmp/dagger-rust-native-deep-artifact-closures','after':'/tmp/dagger-rust-native-plan-decoder'}
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
def debug(route,data=None,timeout=20):
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=timeout)
def mode(name,value):
    with debug(name+'?enabled='+str(value).lower(),b'') as response:assert json.load(response)['enabled']==value

def source_mode(value):
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n' if value else b'off\n',stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)

def cpu_profile():
    with debug('pprof/profile?seconds=25',timeout=40) as response:(root/'engine-cpu.pprof').write_bytes(response.read())

rows=[]
try:
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    mode('direct-span-protobuf',False);mode('snapshot-completions',False)
    source_mode(True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(cpu_profile)
        for index,arm in enumerate(['before','after','after','before','before','after']):
            config.write_text(re.sub(r'source = "[^"]+"','source = '+json.dumps(modules[arm]),original,count=1))
            filename=source/'leaf_1023/src/lib.rs'
            text,count=re.subn(r'pub const EDIT: u64 = \d+;',f'pub const EDIT: u64 = {secrets.randbits(48)};',filename.read_text());assert count==1;filename.write_text(text)
            while True:
                with debug('client-lifecycle') as response:state=json.load(response)
                if not state.get('sessions') and not state['active_requests']:break
                time.sleep(.2)
            time.sleep(1)
            with debug('wcprof/enabled',b'on'):pass
            with debug('wcprof/dump') as response:
                while response.read(1048576):pass
            label=f'{index}-{arm}';captures=[];next_capture=2.;started=time.monotonic();wall_start=time.time()
            with (root/(label+'.log')).open('w') as output:
                process=subprocess.Popen(['python3',str(base/'local_cli_collector.py'),'check','rust:packages/check'],cwd=source,env=env,stdout=output,stderr=subprocess.STDOUT)
                while process.poll() is None:
                    elapsed=time.monotonic()-started
                    if elapsed>=next_capture and len(captures)<8:
                        observed=time.monotonic()
                        try:
                            with debug('pprof/goroutine?debug=2',timeout=5) as response:
                                data=response.read(16*1024*1024);truncated=bool(response.read(1))
                            with gzip.open(root/f'{label}-stack-{len(captures)}.txt.gz','wb') as output_stack:output_stack.write(data)
                            captures.append(dict(offset=elapsed,seconds=time.monotonic()-observed,bytes=len(data),truncated=truncated))
                        except OSError as err:captures.append(dict(offset=elapsed,error=str(err)))
                        next_capture+=2
                    time.sleep(.05)
            seconds=time.monotonic()-started
            with debug('wcprof/enabled',b'off'):pass
            with debug('wcprof/dump') as response,(root/(label+'.ndjson')).open('wb') as output:
                while chunk:=response.read(1048576):output.write(chunk)
            assert process.returncode==0 and 'passed' in (root/(label+'.log')).read_text(),label
            with (root/(label+'.ndjson')).open() as stream:
                header=json.loads(next(stream));strings=header['strings'];ops=[json.loads(line) for line in stream]
            assert not header['dropped_events'] and not header.get('open_ops'),label
            selected=[]
            for op in ops:
                if op.get('e')!='op':continue
                cls=strings[op.get('c',0)];nanos=op['d']-op['s']
                if any(v in cls for v in ['RustCompiler.compile','Directory.glob','Directory.digests','Directory.checkpoint','saveNativeCacheHint','File.export','exec.workload','exec.runContainer','exec.setup','filesync','Host.directory','withExec.prepareMounts','session.flush']):
                    selected.append(dict(id=op.get('id'),parent=op.get('p'),kind=op.get('k'),cls=cls,milliseconds=nanos/1e6,op=op))
            rows.append(dict(label=label,arm=arm,seconds=seconds,wall_start=wall_start,diagnostic_only=True,stack_capture_threshold=2,captures=captures,dropped_events=header['dropped_events'],open_ops=header.get('open_ops',0),selected=selected))
            (root/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
            print(label,round(seconds,3),'seconds; stack captures',len(captures),flush=True)
        future.result()
finally:
    config.write_text(original)
    source_mode(False)
    with debug('wcprof/enabled',b'off'):pass
    mode('batch-metadata',False);mode('attribute-array-decode',False)
