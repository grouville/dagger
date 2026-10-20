"""Compare helper work, excluded from all command timing cohorts."""
from pathlib import Path
from collections import Counter
import gzip
import json
import sys
import time
import urllib.error
import urllib.request

out = Path('/tmp/go-listing-current-main-oct20')
sys.path.insert(0, '/tmp/go-collection-upstream-review-oct19')
import config_dagql_benchmark_helpers as helpers
helpers.out, helpers.cli = out, out / 'main-cli'
info = json.loads((out / 'engine.json').read_text())
engine = helpers.engine_info(info['name'], info['runner'], info['debug'])
directory = out / 'root-path-root-16-wcprof'
directory.mkdir()
root = out / 'root-path-root-16-fixture'
source, test = root / 'pkg_000/value.go', root / 'pkg_000/value_test.go'
original_source, original_test = source.read_bytes(), test.read_bytes()
production = out / 'go-root-path/go.dang'
versions = {'main': (out / 'go-main/go.dang').read_bytes(), 'candidate': production.read_bytes()}

def dump(label, optional=False):
    try:
        with urllib.request.urlopen(engine['debug'] + '/debug/wcprof/dump', timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        if optional and error.code == 503:
            return None
        raise
    (directory / (label + '.ndjson.gz')).write_bytes(gzip.compress(data, mtime=0))
    return data

dump('prior-buffer', optional=True)
records = []
try:
    for arm in ['main', 'candidate']:
        production.write_bytes(versions[arm])
        marker = 'TestProfile' + str(time.time_ns())
        source.write_bytes(original_source + ('\n// Source edit ' + marker + '\n').encode())
        test.write_bytes(original_test.replace(b'func TestValue(', ('func ' + marker + '(').encode(), 1))
        helpers.request(engine['debug'], 'wcprof/enabled', b'on')
        try:
            metrics, text, log = helpers.run('root-path-profile-' + arm, root,
                ['check', '--module', 'go', '--check', 'test', '--list', '--all'], engine)
        finally:
            helpers.request(engine['debug'], 'wcprof/enabled', b'off')
        rows = [line.split()[1:3] for line in text.splitlines() if line.split() and line.split()[0] == 'go']
        expected = [['pkg_' + str(index).zfill(3), marker if index == 0 else 'TestValue'] for index in range(16)]
        assert metrics['cleanup_successful'] and rows == expected
        lines = dump(arm).splitlines()
        header = json.loads(lines[0])
        counter = Counter()
        for line in lines[1:]:
            event = json.loads(line)
            if event['e'] == 'op':
                counter[(event.get('k', ''), header['strings'][event.get('c', 0)], event.get('o', ''))] += 1
        record = dict(arm=arm, profiling=True, excluded_from_timings=True,
                      correct_names_and_order=True, event_count=header['event_count'],
                      dropped_events=header['dropped_events'], open_ops=len(header.get('open_ops', [])),
                      counts=[dict(kind=k, cls=c, outcome=o, count=n) for (k,c,o),n in counter.most_common()],
                      metrics=metrics, log=log)
        assert record['dropped_events'] == 0 and record['open_ops'] == 0
        records.append(record)
        (directory / 'counts.json').write_text(json.dumps(records, indent=2)+'\n')
        print(json.dumps(dict(arm=arm, relevant=[c for c in record['counts'] if c['cls'].endswith('.subpath') or c['cls'].endswith('.packages') or c['cls'].endswith('.tests')])), flush=True)
finally:
    source.write_bytes(original_source)
    test.write_bytes(original_test)
    production.write_bytes(versions['candidate'])
