from pathlib import Path
import hashlib
import json
import subprocess
import time
import urllib.request

root = Path(__file__).parent
base = root.parent
engine = 'dagger-rust-parser-state-pool-oct14'
binary = base / 'config-content-declarations/dagger-engine'

def get(route, data=None):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:16104/debug/' + route, data=data), timeout=30) as response:
        return json.load(response)

state = get('client-lifecycle')
assert not state.get('sessions') and state['active_requests'] == 0
assert not get('config-stat-read?enabled=false&record=false', b'')['enabled']
assert not get('wcprof/enabled')['global_enabled']
assert get('lock-profiler') == dict(mutex_fraction=0, block_profile_rate_ns=0)
expected = '51542ef941c4e3bd96c2ce770c118d154824272ff247d8b9038b0cb27e5fa0e3'
assert hashlib.sha256(binary.read_bytes()).hexdigest() == expected
modes = json.loads((root / 'baseline-modes.json').read_text())
(root / 'candidate-disabled-state.json').write_text(json.dumps(dict(
    mode=get('config-stat-read'), lifecycle=state, profiling=get('wcprof/enabled')), indent=2) + '\n')
command = ['python3', str(base / 'restart_owned_engine_clean.py'), '--engine', engine,
    '--debug-port', '16104', '--output', str(root / 'restore-selected'), '--binary',
    str(binary), '--readiness-timeout', '480']
tick = time.monotonic()
with (root / 'restore-selected.log').open('w') as output:
    result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
(root / 'restore-selected-command.json').write_text(json.dumps(dict(command=command,
    exit_code=result.returncode, seconds=time.monotonic()-tick), indent=2) + '\n')
assert result.returncode == 0
for route, enabled in modes.items():
    assert get(route + '?enabled=' + str(enabled).lower(), b'')['enabled'] == enabled
assert get('builtin-receivers?enabled=true&record=false', b'')['enabled']
assert get('config-declarations?enabled=true&record=false', b'')['enabled']
assert get('usage-sampling')['enabled']
assert get('shared-restored-postings')['enabled'] and get('scalar-array-restore')['enabled']
actual = subprocess.check_output(['docker', 'exec', engine, 'sha256sum', '/usr/local/bin/dagger-engine'], text=True).split()[0]
assert actual == expected
with (root / 'restored-native.log').open('w') as output:
    result = subprocess.run(['python3', str(root / 'verify_retained_first.py'),
        'config-stat-read-restored-first'], stdout=output, stderr=subprocess.STDOUT)
assert result.returncode == 0
routes = list(modes) + ['shared-restored-postings', 'scalar-array-restore',
    'client-lifecycle', 'lock-profiler', 'wcprof/enabled', 'snapshot-collection']
final = {route: get(route) for route in routes}
assert not final['client-lifecycle'].get('sessions') and final['client-lifecycle']['active_requests'] == 0
assert not final['wcprof/enabled']['global_enabled']
assert final['lock-profiler'] == dict(mutex_fraction=0, block_profile_rate_ns=0)
assert not final['snapshot-collection']['deferred']
(root / 'restored-state.json').write_text(json.dumps(dict(engine_sha256=actual,
    same_owned_volume=True, native_histories='All six retain every expected action on the first call after restoring the original selected binary.',
    new_pr_opened=False, state=final), indent=2) + '\n')
print('PASS: original selected binary restored gracefully on the same volume; all six native histories hit on their first call.', flush=True)
