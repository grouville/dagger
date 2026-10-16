from pathlib import Path
import json,subprocess,time,urllib.request

root=Path(__file__).parent;base=root.parent;rows=[]
def run(label,command):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as stream:r=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
    rows.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-started))
    (root/'measurement-phases.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,r.returncode,round(rows[-1]['seconds'],1),flush=True);assert r.returncode==0,label
def mode(name,enabled):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+name+'?enabled='+str(enabled).lower(),data=b''),timeout=15) as r:assert json.load(r)['enabled']==enabled
assert (root/'identity.json').exists()
run('restart-driver',['python3',str(base/'restart_owned_engine_clean.py'),'--engine','dagger-rust-parser-state-pool-oct14','--debug-port','16104','--output',str(root/'restart'),'--binary',str(root/'dagger-engine'),'--readiness-timeout','300'])
actual=subprocess.check_output(['docker','exec','dagger-rust-parser-state-pool-oct14','sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0];assert actual==json.loads((root/'identity.json').read_text())['engine_sha256']
mode('dimension-key-fields',True)
run('commands-driver',['python3',str(root/'measure_commands.py'),'--output-root',str(root/'commands'),'--pairs','8'])
run('confirmation-driver',['python3',str(root/'confirm_commands.py'),'--output-root',str(root/'confirmation'),'--pairs','8'])
run('profiles-driver',['python3',str(root/'profile_commands.py'),'--output-root',str(root/'profiles'),'--pairs','1','--kinds','large','list'])
try:
    mode('typed-proto-fields',True)
    run('retained-cache',['python3',str(base/'check_native_discovery_current_reuse.py'),'typed-proto-fields'])
finally:mode('typed-proto-fields',False)
