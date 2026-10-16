from pathlib import Path
import json, os, secrets, subprocess, time, urllib.request

root=Path(__file__).parent; base=root.parent
def mode(name, enabled):
    req=urllib.request.Request('http://127.0.0.1:16104/debug/'+name+'?enabled='+str(enabled).lower(),data=b'')
    with urllib.request.urlopen(req,timeout=20) as r: assert json.load(r)['enabled']==enabled

removed={'DAGGER_SESSION_PORT','DAGGER_SESSION_TOKEN','DAGGER_CLOUD_TOKEN','DAGGER_CLOUD_URL','DAGGER_ENGINE','DAGGER_CLOUD_ENGINE','SSH_AUTH_SOCK','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'}
env={k:v for k,v in os.environ.items() if k not in removed and not k.startswith('OTEL_EXPORTER_')}
env.update(DAGGER_CLOUD_URL='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184',DAGGER_CLOUD_TOKEN='local-benchmark-token',XDG_CONFIG_HOME='/tmp/rust-cache-oct13-filter/local-client-config',NO_PROXY='*',_EXPERIMENTAL_DAGGER_RUNNER_HOST='tcp://127.0.0.1:16276')
mode('dimension-key-fields',True);mode('artifact-metadata-fields',True)
rows=[]
try:
    for enabled in [False,True]:
        mode('digest-paths-mount',enabled)
        label='validation-'+str(enabled)+'-'+secrets.token_hex(4)
        tick=time.monotonic()
        with (root/('validation-'+str(enabled)+'.log')).open('w') as output:
            result=subprocess.run([str(base/'dagger-artifact-list-buffered'),'run','--',str(root/'probe'),label],cwd='/tmp',env=env,stdout=output,stderr=subprocess.STDOUT)
        rows.append(dict(enabled=enabled,exit_code=result.returncode,seconds=time.monotonic()-tick,label=label))
        (root/'validation.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(rows[-1],flush=True)
        assert result.returncode==0,'See bounded validation log'
finally:
    mode('digest-paths-mount',False)
