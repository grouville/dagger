from pathlib import Path
import json
import subprocess
import sys
import time
import urllib.request

root=Path(__file__).parent
phase=sys.argv[1]
assert phase in ['post-cohort','post-capture']
def mode(enabled=None):
    route='http://127.0.0.1:16104/debug/trivial-scalar-fields'
    request=urllib.request.Request(route if enabled is None else route+'?enabled='+str(enabled).lower(),data=None if enabled is None else b'')
    with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
before=mode()['enabled']
command=['python3',str(root/'verify_retained_first.py'),'scalar-projection-'+phase]
begin=time.monotonic()
try:
    assert mode(True)['enabled']
    with (root/(phase+'-native.log')).open('w') as stream:result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
    (root/(phase+'-native.json')).write_text(json.dumps(dict(command=command,seconds=time.monotonic()-begin,exit_code=result.returncode,candidate_enabled=mode()['enabled']),indent=2)+'\n')
    assert result.returncode==0
finally:
    assert mode(before)['enabled']==before
print('PASS: all six native histories retained with candidate enabled.',flush=True)
