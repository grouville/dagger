from pathlib import Path
import json
import subprocess
import sys

sys.path.insert(0, '/tmp/rust-cache-sipsma-review/cache-usage-minimal-engine')
from bench_engine import BenchEngine

root = Path(__file__).parent
engine = BenchEngine(root)
engine.idle('post-cohort-native-histories')
for route in ['builtin-receivers', 'usage-sampling', 'reusable-declarations',
              'restored-posting-removal', 'span-lookup-fanout']:
    engine.mode(route, True)
assert not engine.get('builtin-receivers?enabled=true&record=false', b'')['record']
with (root/'post-cohort-native.log').open('w') as out:
    command = ['python3', str(root/'verify_retained_first.py'), 'builtin-receivers-post-cohort']
    result = subprocess.run(command, stdout=out, stderr=subprocess.STDOUT)
(root/'post-cohort-native.json').write_text(json.dumps(dict(command=command,
    exit_code=result.returncode), indent=2)+'\n')
assert result.returncode == 0, (root/'post-cohort-native.log').read_text()[-2000:]
routes = ['builtin-receivers', 'usage-sampling', 'reusable-declarations',
          'restored-posting-removal', 'span-lookup-fanout', 'prepared-schema',
          'single-toml-parse', 'span-resource-batches', 'callback-caller-reuse',
          'telemetry-flush-coalescing', 'lazy-type-maps', 'batch-metadata',
          'attribute-array-decode', 'direct-span-protobuf']
state = {route: engine.get(route) for route in routes}
state.update(client_lifecycle=engine.get('client-lifecycle'),
             wcprof=engine.get('wcprof/enabled'),
             lock_profiler=engine.get('lock-profiler'),
             snapshot_collection=engine.get('snapshot-collection'))
assert not state['client_lifecycle'].get('sessions') and state['client_lifecycle']['active_requests']==0
assert not state['wcprof']['global_enabled']
assert state['lock_profiler'] == dict(mutex_fraction=0, block_profile_rate_ns=0)
assert not state['snapshot_collection']['deferred']
(root/'selected-state.json').write_text(json.dumps(state, indent=2)+'\n')
print('PASS: six native histories retained after full listings and host-read tracing; selected method calls enabled, counters and profiling off, ordinary GC enabled.', flush=True)
