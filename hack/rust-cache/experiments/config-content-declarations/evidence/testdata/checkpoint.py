from pathlib import Path
import json
import subprocess
import urllib.request

root = Path(__file__).parent
work = Path('/tmp/dagger-config-declarations-only')
command = ['python3', str(root/'verify_retained_first.py'), 'config-declarations-post-capture']
with (root/'post-capture-native.log').open('w') as out:
    result = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT)
(root/'post-capture-native.json').write_text(json.dumps(dict(command=command,
    exit_code=result.returncode), indent=2)+'\n')
assert result.returncode == 0
routes = ['config-declarations', 'builtin-receivers', 'usage-sampling',
          'reusable-declarations', 'restored-posting-removal', 'span-lookup-fanout',
          'single-toml-parse', 'prepared-schema', 'callback-caller-reuse',
          'telemetry-flush-coalescing', 'direct-span-protobuf',
          'client-lifecycle', 'lock-profiler', 'wcprof/enabled', 'snapshot-collection']
state = {}
for route in routes:
    with urllib.request.urlopen('http://127.0.0.1:16104/debug/'+route, timeout=20) as response:
        state[route] = json.load(response)
assert state['config-declarations']['enabled'] and not state['config-declarations']['record']
assert state['builtin-receivers']['enabled'] and state['usage-sampling']['enabled']
assert not state['client-lifecycle'].get('sessions') and state['client-lifecycle']['active_requests']==0
assert not state['wcprof/enabled']['global_enabled']
assert state['lock-profiler'] == dict(mutex_fraction=0, block_profile_rate_ns=0)
assert not state['snapshot-collection']['deferred']
(root/'selected-state.json').write_text(json.dumps(state, indent=2)+'\n')
(root/'standalone.patch').write_bytes(subprocess.check_output(['git', 'show', '--format=fuller', 'HEAD'], cwd=work))
progress = dict(previous_turn='progress', stage='Content-keyed declarations validated, measured, selected and pushed as an isolated branch.',
    goal_status='Active; full Go listing and integrated Rust performance targets remain incomplete.',
    full_command=json.loads((root/'full-command-paired/summary.json').read_text()),
    standalone=json.loads((root/'standalone-identity.json').read_text()),
    profiling=json.loads((root/'capture/result.json').read_text())['recorder'],
    native_histories='All six retained before/after restart, after the cohort and after profiling.',
    next_targets=['Evaluate read-first host configuration lookup with stat reserved for failure classification.',
                  'Compare existing direct-span and callback-scope prototypes on full Go listing.'],
    new_pr_opened=False)
(root/'progress.json').write_text(json.dumps(progress, indent=2)+'\n')
print('PASS: native histories retained, selected engine idle, telemetry/GC enabled, profiling off.', flush=True)
subprocess.run(['python3', str(root/'archive.py')], check=True)
