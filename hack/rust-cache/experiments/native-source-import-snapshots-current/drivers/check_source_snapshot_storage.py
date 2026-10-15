import base64
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

base=Path('/tmp/rust-cache-sipsma-review')
root=base/'source-snapshot-storage-current'
root.mkdir(exist_ok=False)
engine='dagger-rust-parser-state-pool-oct14'
endpoint='http://127.0.0.1:16104'
env=dict(os.environ,RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'),RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',_EXPERIMENTAL_DAGGER_CLI_BIN=str(base/'dagger-artifact-workspace-before'))

def mode(enabled):
    subprocess.run(['docker','exec','-i',engine,'sh','-c','cat > /tmp/filesync-snapshot-seeds-mode'],input=b'on\n' if enabled else b'off\n',check=True)

def idle():
    started=time.monotonic()
    while True:
        with urllib.request.urlopen(endpoint+'/debug/client-lifecycle',timeout=10) as response:state=json.load(response)
        if not state.get('sessions') and not state['active_requests']:return
        assert time.monotonic()-started<120,'engine not idle'
        time.sleep(.25)

def varint(data,pos):
    value=0
    for shift in range(0,70,7):
        byte=data[pos];pos+=1;value|=(byte&127)<<shift
        if byte<128:return value,pos
    raise AssertionError('invalid varint')


def handle(encoded):
    data=base64.b64decode(encoded,validate=True)
    assert data[0]==18,'expected engineResult ID'
    size,pos=varint(data,1)
    assert pos+size==len(data) and data[pos]==8,'invalid engineResult encoding'
    number,_=varint(data,pos+1)
    return number


try:
    for variant in ['full','seed']:
        source=root/('source-'+variant)
        shutil.copytree('/tmp/rust-native-config-entry-1026-before',source,ignore=shutil.ignore_patterns('.git','target','dagger.lock'))
        (source/'storage-variant.txt').write_text(variant+'\n')
        mode(variant=='seed')
        idle()
        with (root/(variant+'.log')).open('w') as log:
            result=subprocess.run(['python3',str(base/'local_cli_collector.py'),'api','with-session','--',str(base/'source-snapshot-storage'),'-source',str(source),'-output',str(root/(variant+'-ids.json')),'-edits','19'],cwd='/tmp/dagger-rust-local-package-fingerprint',env=env,stdout=log,stderr=subprocess.STDOUT)
        assert result.returncode==0,variant
        print('PASS',variant,'19 fresh imports and old snapshot contents',flush=True)
    mode(False)
    idle()
    with urllib.request.urlopen(endpoint+'/debug/dagql/cache',timeout=120) as response:
        data=response.read()
    graph=json.loads(data)
    assert not graph.get('session_results')
    selected={side:[handle(row['id']) for row in json.loads((root/(side+'-ids.json')).read_text())] for side in ['full','seed']}
    needed=set(selected['full']+selected['seed'])
    nodes={row['shared_result_id']:row for row in graph['results'] if row['shared_result_id'] in needed}
    assert len(nodes)==len(needed),(len(nodes),len(needed))
    (root/'selected-results.json').write_text(json.dumps(nodes,indent=2)+'\n')
    del data,graph
    idle()
    subprocess.run(['docker','pause',engine],check=True,stdout=subprocess.DEVNULL)
    try:
        subprocess.run(['docker','cp',engine+':/var/lib/dagger/worker/snapshots/metadata.db',str(root/'metadata.db')],check=True)
    finally:
        subprocess.run(['docker','unpause',engine],check=True,stdout=subprocess.DEVNULL)
    with (root/'snapshot-metadata.json').open('w') as output:
        subprocess.run([str(base/'snapshot-ancestry'),str(root/'metadata.db')],check=True,stdout=output)
    infos=json.loads((root/'snapshot-metadata.json').read_text())
    rows=[]
    for variant,ids in selected.items():
        chains=[]
        for number in ids:
            links=nodes[number]['snapshot_links'];assert len(links)==1,(number,links)
            at=links[0]['RefKey'];chain=[]
            while at:
                assert at not in chain and at in infos,at
                chain.append(at);at=infos[at]['parent']
            chains.append(chain)
        assert [len(chain)-1 for chain in chains]==([0]*19 if variant=='full' else [i%9 for i in range(19)]),(variant,list(map(len,chains)))
        for selection,selected_chains in [('all_19_imports',chains),('latest_only',[chains[-1]]),('before_periodic_reset',[chains[17]])]:
            seen=sorted({item for chain in selected_chains for item in chain})
            paths=['/var/lib/dagger/worker/snapshots/snapshots/'+infos[item]['storage_id']+'/fs' for item in seen]
            measured=subprocess.run(['docker','exec',engine,'du','-s','-k','-c',*paths],check=True,text=True,stdout=subprocess.PIPE)
            (root/(variant+'-'+selection+'-du.txt')).write_text(measured.stdout)
            row=dict(variant=variant,selection=selection,physical_snapshots=len(seen),allocated_bytes=int(measured.stdout.splitlines()[-1].split()[0])*1024,recorded_bytes=sum(infos[item]['size'] for item in seen),max_chain=max(map(len,selected_chains)),chains=selected_chains)
            rows.append(row)
            print({k:row[k] for k in row if k!='chains'},flush=True)
    (root/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('PASS: real overlay storage and bounded ancestry; engine unpaused; source seeds off',flush=True)
finally:
    mode(False)
