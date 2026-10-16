from pathlib import Path
import hashlib,json,os,re,secrets,subprocess,time,urllib.request

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'listing-allocation-stacks'
root.mkdir(exist_ok=False)
debug='http://127.0.0.1:16104/debug/'
source=Path('/tmp/rust-native-config-entry-1026-before')
def get(route,data=None):
    with urllib.request.urlopen(urllib.request.Request(debug+route,data=data),timeout=90) as response:return json.load(response)
def mode(route,enabled):assert get(route+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
def profile(route,name):
    started=time.monotonic()
    with urllib.request.urlopen(debug+'pprof/'+route,timeout=90) as response:(root/name).write_bytes(response.read())
    return time.monotonic()-started
def flush(label):
    rows=[]
    for n in range(2):rows.append(profile('heap?gc=1',label+f'-gc-{n}.heap.pprof'))
    return rows

removed={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
try:
    assert not get('client-lifecycle')['sessions']
    assert not get('wcprof/enabled')['global_enabled']
    assert get('dimension-key-fields')['enabled']
    assert not get('parallel-fingerprint')['enabled']
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    edit=secrets.randbits(48);filename=source/'leaf_1023/src/lib.rs'
    text,count=re.subn(r'pub const EDIT: u64 = \d+;',f'pub const EDIT: u64 = {edit};',filename.read_text());assert count==1;filename.write_text(text)
    before_gc=flush('before');profile('allocs','before.allocs.pprof');before=get('vars')['memstats']
    started=time.time()
    with (root/'listing.log').open('w') as output:result=subprocess.run([str(base/'dagger-artifact-list-buffered'),'check','--list','--all','rust:packages/check'],cwd=source,env=env,stdout=output,stderr=subprocess.STDOUT)
    ended=time.time();after=get('vars')['memstats']
    assert result.returncode==0
    listed=re.findall(r'^rust\s+(\S+)\s+check$',(root/'listing.log').read_text(),re.M)
    assert len(listed)==1026 and set(listed)==({'app','shared'}|{f'leaf_{n:04d}' for n in range(1024)})
    after_gc=flush('after');profile('allocs','after.allocs.pprof')
    (root/'metadata.json').write_text(json.dumps(dict(scope='Allocation-stack attribution only. Two explicit Go GCs before and after flush delayed allocation samples; elapsed command time is not a performance result. Cache GC stays ordinary and can contribute separate background stacks.',before_gc_seconds=before_gc,after_gc_seconds=after_gc,command_start=started,command_end=ended,source_edit_value=edit,engine_sha256=subprocess.check_output(['docker','exec','dagger-rust-parser-state-pool-oct14','sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0],module_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd='/tmp/dagger-rust-native-discovery-current',text=True).strip(),command_allocated_bytes=after['TotalAlloc']-before['TotalAlloc'],command_Go_GCs=after['NumGC']-before['NumGC'],snapshot_collection=get('snapshot-collection')),indent=2)+'\n')
    print('PASS: 1026 rows, allocation samples flushed; command allocated bytes',after['TotalAlloc']-before['TotalAlloc'],flush=True)
finally:
    mode('batch-metadata',False);mode('attribute-array-decode',False)
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True)
