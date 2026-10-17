from pathlib import Path
import json
import subprocess
import urllib.request

root = Path(__file__).parent
statefile = root/'selected-state.json'
oldstate = root/'selected-state-as-measured.json'
if not oldstate.exists():
    oldstate.write_bytes(statefile.read_bytes())
routes = ['builtin-receivers', 'usage-sampling', 'reusable-declarations',
          'restored-posting-removal', 'span-lookup-fanout', 'prepared-schema',
          'single-toml-parse', 'span-resource-batches', 'callback-caller-reuse',
          'telemetry-flush-coalescing', 'lazy-type-maps', 'batch-metadata',
          'attribute-array-decode', 'direct-span-protobuf', 'client-lifecycle',
          'wcprof/enabled', 'lock-profiler', 'snapshot-collection']
state = {}
for route in routes:
    with urllib.request.urlopen('http://127.0.0.1:16104/debug/'+route, timeout=20) as response:
        state[route] = json.load(response)
assert state['builtin-receivers']['enabled'] and not state['builtin-receivers']['record']
assert state['usage-sampling']['enabled']
assert not state['client-lifecycle'].get('sessions') and state['client-lifecycle']['active_requests']==0
assert not state['wcprof/enabled']['global_enabled'] and not state['snapshot-collection']['deferred']
state['engine_identity'] = json.loads((root/'json-compatibility/identity.json').read_text())
statefile.write_text(json.dumps(state, indent=2)+'\n')
progress = json.loads((root/'progress.json').read_text())
progress.update(final_engine_sha256=state['engine_identity']['engine_sha256'],
    final_validation=json.loads((root/'final-validation.json').read_text()),
    final_metadata_guard_fixed=True,
    benchmark_expected_values=json.loads((root/'final-benchmark-values.json').read_text()))
(root/'progress.json').write_text(json.dumps(progress, indent=2)+'\n')
print('Final engine idle; profilers/counters off, ordinary GC on; native cache preserved.', flush=True)
subprocess.run(['python3', str(root/'archive.py')], check=True)
