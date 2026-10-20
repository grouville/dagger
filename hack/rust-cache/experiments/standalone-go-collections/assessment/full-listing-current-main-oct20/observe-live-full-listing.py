"""Sample the remaining cost in the already-running full-output smoke."""
from pathlib import Path
from collections import Counter
import gzip
import json
import os
import time
import urllib.request

out = Path('/tmp/go-listing-current-main-oct20')
state = json.loads((out / 'full-listing-process.json').read_text())
assert state['state'] == 'running'
pid = state['driver_pid']
assert b'/tmp/go-listing-current-main-oct20/run-full-listing-sort.py' in Path('/proc/' + str(pid) + '/cmdline').read_bytes()
os.kill(state['helper_pid'], 0)
info = json.loads((out / 'engine.json').read_text())
directory = out / 'full-listing-live-profile'
directory.mkdir(exist_ok=False)
def fetch(path, data=None):
    with urllib.request.urlopen(info['debug'] + '/debug/' + path, data=data, timeout=40) as response:
        return response.read()
assert not json.loads(fetch('wcprof/enabled'))['global_enabled']
prior = fetch('wcprof/dump')
(directory / 'prior-buffer.ndjson.gz').write_bytes(gzip.compress(prior, mtime=0))
record = dict(label=state['label'], process=state, profiling=True,
              purpose='diagnostic window inside full-output smoke; exclude from timing comparisons',
              started_unix=time.time(), original_driver_profiler_flag=False)
(out / 'full-listing-observer.json').write_text(json.dumps(record, indent=2)+'\n')
fetch('wcprof/enabled', b'on')
try:
    (directory / 'goroutines.txt.gz').write_bytes(gzip.compress(fetch('pprof/goroutine?debug=2'), mtime=0))
    start = time.monotonic()
    (directory / 'engine-cpu.pprof').write_bytes(fetch('pprof/profile?seconds=15'))
    while time.monotonic()-start < 45:
        # Short waits let the capture stop if its own command has exited.
        time.sleep(1)
        if not Path('/proc/' + str(state['helper_pid'])).exists():
            break
finally:
    fetch('wcprof/enabled', b'off')
data = fetch('wcprof/dump')
(directory / 'window.ndjson.gz').write_bytes(gzip.compress(data, mtime=0))
lines = data.splitlines()
header = json.loads(lines[0])
counts = Counter()
for line in lines[1:]:
    event = json.loads(line)
    if event['e']=='op':
        counts[(event.get('k',''),header['strings'][event.get('c',0)],event.get('o',''))] += 1
record.update(ended_unix=time.time(), event_count=header['event_count'], dropped_events=header['dropped_events'],
              open_ops=header.get('open_ops',[]), counts=[dict(kind=k,cls=c,outcome=o,count=n) for (k,c,o),n in counts.most_common()])
(directory / 'result.json').write_text(json.dumps(record, indent=2)+'\n')
(out / 'full-listing-observer.json').write_text(json.dumps({k:v for k,v in record.items() if k!='counts'}, indent=2)+'\n')
print(json.dumps(dict(event_count=record['event_count'],dropped_events=record['dropped_events'],open_ops=len(record['open_ops']),calls=[c for c in record['counts'] if c['kind']=='call_exec'])),flush=True)
