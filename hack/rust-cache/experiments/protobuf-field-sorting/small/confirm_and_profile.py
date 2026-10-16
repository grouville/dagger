from pathlib import Path
import json,subprocess,time,urllib.request

root=Path(__file__).parent;base=root.parent;rows=[]
def run(label,command):
    started=time.monotonic()
    with (root/(label+'.log')).open('w') as out:r=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT)
    rows.append(dict(label=label,command=command,exit_code=r.returncode,seconds=time.monotonic()-started))
    (root/'post-validation.json').write_text(json.dumps(rows,indent=2)+'\n');print(label,r.returncode,round(rows[-1]['seconds'],2),flush=True)
    assert r.returncode==0,label
def mode(enabled):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/small-proto-fields?enabled='+str(enabled).lower(),data=b''),timeout=10) as response:assert json.load(response)['enabled']==enabled
assert (root/'commands/summary.json').exists()
run('confirmation-driver',['python3',str(root/'confirm_commands.py'),'--output-root',str(root/'confirmation'),'--pairs','8'])
run('profiles-driver',['python3',str(root/'profile_commands.py'),'--output-root',str(root/'profiles'),'--pairs','1','--kinds','large','list'])
run('standalone-driver',['python3',str(root/'measure_standalone.py')])
try:
    mode(True)
    run('retained-cache',['python3',str(base/'check_native_discovery_current_reuse.py'),'small-proto-fields'])
finally:mode(False)
