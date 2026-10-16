from pathlib import Path
import json,os,statistics,subprocess,time,urllib.request

root=Path(__file__).parent;base=root.parent
removed={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','SSH_AUTH_SOCK','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
phases=[]
def mode(name,enabled):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+name+'?enabled='+str(enabled).lower(),data=b''),timeout=20) as r:assert json.load(r)['enabled']==enabled
def run(label,command):
    tick=time.monotonic()
    with (root/(label+'.log')).open('w') as output:r=subprocess.run(command,cwd='/tmp',env=env,stdout=output,stderr=subprocess.STDOUT)
    phases.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-tick))
    (root/'phases.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(phases[-1],flush=True)
    assert r.returncode==0,label
try:
    assert subprocess.check_output(['docker','exec','dagger-rust-parser-state-pool-oct14','sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]==json.loads((root/'identity.json').read_text())['engine_sha256']
    mode('dimension-key-fields',True);mode('artifact-metadata-fields',True)
    run('components',[str(base/'dagger-artifact-list-buffered'),'run','--',str(root/'bench')])
    data=next(json.loads(line) for line in (root/'components.log').read_text().splitlines() if line.startswith('{"each_query_has_fresh_parent"') or line.startswith('{"rows"'))
    (root/'component-runs.json').write_text(json.dumps(data,indent=2)+'\n')
    summary={}
    for count in [1,130,1026]:
        rows=[r for r in data['rows'] if r['count']==count]
        savings=[next(r['seconds'] for r in rows if r['pair']==pair and not r['enabled'])-next(r['seconds'] for r in rows if r['pair']==pair and r['enabled']) for pair in range(6)]
        summary[count]=dict(medians={str(enabled):statistics.median(r['seconds'] for r in rows if r['enabled']==enabled) for enabled in [False,True]},median_paired_saving=statistics.median(savings),faster_pairs=sum(s>0 for s in savings))
    (root/'component-summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(summary,flush=True)
    mode('digest-paths-mount',False)
    run('commands-driver',['python3',str(root/'measure_commands.py'),'--output-root',str(root/'commands'),'--pairs','8'])
    run('profiles-driver',['python3',str(root/'profile_commands.py'),'--output-root',str(root/'profiles'),'--pairs','1','--kinds','large','direct'])
finally:
    mode('digest-paths-mount',False)
