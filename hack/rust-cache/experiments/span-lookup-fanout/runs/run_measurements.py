from pathlib import Path
import json,subprocess,time,urllib.request

root=Path(__file__).parent;base=root.parent;phases=[]
def run(label,command):
    tick=time.monotonic()
    with (root/(label+'.log')).open('w') as output:r=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT)
    phases.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-tick));(root/'measurement-phases.json').write_text(json.dumps(phases,indent=2)+'\n')
    print(phases[-1],flush=True);assert r.returncode==0,label
def mode(name,enabled):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+name+'?enabled='+str(enabled).lower(),data=b''),timeout=20) as r:assert json.load(r)['enabled']==enabled

run('restart-driver',['python3',str(base/'restart_owned_engine_clean.py'),'--engine','dagger-rust-parser-state-pool-oct14','--debug-port','16104','--output',str(root/'restart'),'--binary',str(root/'dagger-engine'),'--readiness-timeout','300'])
assert subprocess.check_output(['docker','exec','dagger-rust-parser-state-pool-oct14','sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]==json.loads((root/'identity.json').read_text())['engine_sha256']
mode('dimension-key-fields',True);mode('artifact-metadata-fields',True)
try:
    run('commands-driver',['python3',str(root/'measure_commands.py'),'--output-root',str(root/'commands'),'--pairs','8'])
    run('profiles-driver',['python3',str(root/'profile_commands.py'),'--output-root',str(root/'profiles'),'--pairs','1','--kinds','large','list'])
finally:mode('span-lookup-fanout',False)
