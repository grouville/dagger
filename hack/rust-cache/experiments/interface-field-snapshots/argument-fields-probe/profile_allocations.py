from pathlib import Path
import json
import os
import re
import secrets
import subprocess
import time
import urllib.request

root=Path(__file__).parent/'allocation-profile';root.mkdir(exist_ok=False)
base=root.parent.parent
source=base/'rust-go-test-collections/fixtures/rust-64'
config=source/'dagger.toml';original=config.read_bytes()
debug='http://127.0.0.1:16104/debug/'
def request(path,data=None):
    with urllib.request.urlopen(urllib.request.Request(debug+path,data=data),timeout=30) as response:return response.read()
def mode(name,enabled):
    assert json.loads(request(name+'?enabled='+str(enabled).lower(),b''))['enabled']==enabled
removed={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276',_EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
command=[str(base/'dagger-artifact-list-buffered'),'check','rust:packages/tests/test']
try:
    state=json.loads(request('client-lifecycle'));assert not state.get('sessions') and state['active_requests']==0
    assert not json.loads(request('wcprof/enabled'))['global_enabled']
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    config.write_text(re.sub(r'source = "[^"]+"','source = "/tmp/dagger-rust-test-collection-batched-inputs"',original.decode(),count=1))
    file=source/'pkg_000/src/lib.rs';value=secrets.randbits(48)+1
    text,n=re.subn(r'pub fn edited_value\(\) -> u64 \{ \d+ \}',f'pub fn edited_value() -> u64 {{ {value} }}',file.read_text());assert n==1;file.write_text(text)
    before=json.loads(request('vars'))['memstats'];(root/'before.pprof').write_bytes(request('pprof/allocs'))
    start=time.time()
    with (root/'command.log').open('w') as out:result=subprocess.run(command,cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT)
    end=time.time();(root/'after.pprof').write_bytes(request('pprof/allocs'));after=json.loads(request('vars'))['memstats']
    (root/'result.json').write_text(json.dumps(dict(command=command,exit_code=result.returncode,unix_start=start,unix_end=end,edit_value=value,telemetry=True,wcprof=False,forced_gc=False,allocated_bytes=after['TotalAlloc']-before['TotalAlloc'],gc_cycles=after['NumGC']-before['NumGC'],profile_scope='Cumulative allocation samples before/after one edited command; samples can lag natural GC and are diagnostic, not exact accounting.'),indent=2)+'\n')
    assert result.returncode==0
finally:
    config.write_bytes(original);mode('batch-metadata',False);mode('attribute-array-decode',False)
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True)
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
for cumulative in [False,True]:
    args=[go,'tool','pprof','-sample_index=alloc_space','-base',str(root/'before.pprof'),'-top','-nodecount=65']+(['-cum'] if cumulative else [])+[str(root/'after.pprof')]
    with (root/('allocation-'+('cum' if cumulative else 'flat')+'.txt')).open('w') as out:subprocess.run(args,stdout=out,stderr=subprocess.STDOUT,check=True)
print((root/'result.json').read_text(),flush=True)
