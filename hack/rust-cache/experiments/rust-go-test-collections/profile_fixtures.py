from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import os
import re
import secrets
import subprocess
import time
import urllib.request

home=Path(__file__).parent;base=home.parent;root=home/'profiles-sixteen';root.mkdir(exist_ok=False)
debug='http://127.0.0.1:16104/debug/'
def get(route,data=None):
    with urllib.request.urlopen(urllib.request.Request(debug+route,data=data),timeout=30) as response:return json.load(response)
def mode(name,enabled):assert get(name+'?enabled='+str(enabled).lower(),b'')['enabled']==enabled
def cpu_profile(label):
    tick=time.time()
    with urllib.request.urlopen(debug+'pprof/profile?seconds=5',timeout=15) as r:(root/(label+'.pprof')).write_bytes(r.read())
    return dict(start=tick,end=time.time(),scope='Five-second window includes post-command idle time for short commands.')
def drain(label):
    chunks=[];start=time.monotonic()
    while True:
        with urllib.request.urlopen(debug+'wcprof/dump',timeout=30) as r:raw=r.read()
        with gzip.open(root/f'{label}-chunk-{len(chunks)}.ndjson.gz','wb') as out:out.write(raw)
        lines=raw.splitlines();header=json.loads(lines[0]);chunks.append((header,lines[1:]))
        assert header['dropped_events']==0,label
        if not header.get('open_ops'):break
        assert time.monotonic()-start<45,'open recorder work after completion'
        time.sleep(.2)
    final=dict(chunks[-1][0]);events=[]
    for header,lines in chunks:
        assert final['strings'][:len(header['strings'])]==header['strings']
        events.extend(lines)
    final['event_count']=len(events)
    with (root/(label+'.ndjson')).open('wb') as out:
        out.write((json.dumps(final)+'\n').encode());out.write(b'\n'.join(events)+b'\n')
    return dict(events=len(events),chunks=len(chunks),dropped=final['dropped_events'],open=len(final.get('open_ops',[])))
removed={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','SSH_AUTH_SOCK','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276',_EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))
rows=[]
try:
    mode('batch-metadata',True);mode('attribute-array-decode',True)
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n',check=True)
    for language,arm in [('rust','batch'),('rust','collection'),('go','batch'),('go','collection')]:
        source=home/f'fixtures/{language}-16';label=language+'-'+arm
        path=source/('pkg_000/src/lib.rs' if language=='rust' else 'pkg_000/value.go');value=secrets.randbits(48)+1
        if language=='rust':pattern=r'pub fn edited_value\(\) -> u64 \{ \d+ \}';replacement=f'pub fn edited_value() -> u64 {{ {value} }}'
        else:pattern=r'func EditedValue\(\) uint64 \{ return \d+ \}';replacement=f'func EditedValue() uint64 {{ return {value} }}'
        text,n=re.subn(pattern,replacement,path.read_text());assert n==1;path.write_text(text)
        while get('client-lifecycle').get('sessions'):time.sleep(.2)
        get('wcprof/enabled',b'on')
        with urllib.request.urlopen(debug+'wcprof/dump',timeout=30) as r:r.read()
        if language=='rust':command=[str(base/'dagger-artifact-list-buffered'),'check','rust:test' if arm=='batch' else 'rust:packages/tests/test']
        elif arm=='batch':command=[str(base/'dagger-artifact-list-buffered'),'api','call','go','module','--path=.','test']
        else:command=[str(base/'dagger-artifact-list-buffered'),'check','go:packages/tests/test']
        with ThreadPoolExecutor(max_workers=1) as pool:
            capture=pool.submit(cpu_profile,label);start=time.time()
            with (root/(label+'.log')).open('w') as out:result=subprocess.run(command,cwd=source,env=env,stdout=out,stderr=subprocess.STDOUT)
            end=time.time();get('wcprof/enabled',b'off');recorder=drain(label);window=capture.result()
        rows.append(dict(label=label,exit_code=result.returncode,diagnostic_seconds=end-start,command=command,edit_value=value,cpu_window=window,recorder=recorder))
        (root/'results.json').write_text(json.dumps(rows,indent=2)+'\n');assert result.returncode==0,label
        print(label,round(end-start,3),recorder,flush=True)
finally:
    get('wcprof/enabled',b'off');mode('batch-metadata',False);mode('attribute-array-decode',False)
    subprocess.run(['docker','exec','-i','dagger-rust-parser-state-pool-oct14','sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'off\n',check=True)
