from pathlib import Path
import hashlib
import json
import subprocess
import time
import urllib.request

root = Path(__file__).parent
engine = 'dagger-rust-parser-state-pool-oct14'
state = json.loads(subprocess.check_output(['docker', 'inspect', engine]))[0]['State']
assert not state['Running'] and state['ExitCode'] == 2 and not state['OOMKilled'], state
(root/'prototype-crash-state.json').write_text(json.dumps(state, indent=2)+'\n')
binary = root/'dagger-engine-fixed-identity'
subprocess.run(['docker','cp',str(binary),engine+':/usr/local/bin/dagger-engine'],check=True)
subprocess.run(['docker','start',engine],check=True)
started = time.monotonic()
def get(route, data=None):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/'+route,data=data),timeout=3) as r:
        return json.load(r)
while True:
    try:
        assert not get('reusable-declarations')['enabled']
        break
    except OSError:
        assert time.monotonic()-started < 480, 'engine readiness timeout'
        time.sleep(.25)
for route, enabled in json.loads((root/'baseline-modes.json').read_text()).items():
    assert get(route+'?enabled='+str(enabled).lower(),b'')['enabled'] == enabled
assert not get('snapshot-collection')['deferred']
assert get('collection-expansion-limit')['limit'] == 0
digest = subprocess.check_output(['docker','exec',engine,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0]
assert digest == hashlib.sha256(binary.read_bytes()).hexdigest()
(root/'recovery.json').write_text(json.dumps(dict(engine_sha256=digest,
    startup_seconds=time.monotonic()-started,default_enabled=False,
    note='Restored the same stopped engine and its volume after the prototype panic; no cache was deleted or reset.'),indent=2)+'\n')
print('Engine ready; declaration reuse is off.',flush=True)
with (root/'retained-recovery.log').open('w') as out:
    result = subprocess.run(['python3',str(root/'verify_retained_strict.py'),'reusable-declarations-recovered'],stdout=out,stderr=subprocess.STDOUT)
assert result.returncode == 0, 'retained Rust history check failed'
print('All six retained Rust histories passed strict reuse without preparation.',flush=True)
