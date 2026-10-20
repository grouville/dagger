"""Verify both variants execute the owned-file operation; exclude timings."""
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
directory = out / 'sort-owned-files-wcprof'
directory.mkdir(exist_ok=False)
root = Path('/tmp/dagger-go-collection-current-main')
config, source = root / 'dagger.toml', root / 'dagql/types.go'
original_config, original_source = config.read_bytes(), source.read_bytes()
module = out / 'go-sorted-inputs'
names = ['go.dang', 'gomod/main.dang']
versions = {arm: {name: (out / ('go-main' if arm == 'main' else 'go-sorted-inputs') / name).read_bytes()
                   for name in names} for arm in ['main', 'candidate']}
expected = json.loads((out / 'owned-file-inventory.json').read_text())['files']

def dump(label, optional=False):
    try:
        with urllib.request.urlopen(engine['debug'] + '/debug/wcprof/dump', timeout=60) as response:
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
    config.write_text('[modules.gomod]\nsource = "' + str(module / 'gomod') + '"\n')
    for arm in ['main', 'candidate']:
        for name in names:
            (module / name).write_bytes(versions[arm][name])
        source.write_bytes(original_source + ('\n// Owned-file work verification ' + str(time.time_ns()) + '\n').encode())
        helpers.request(engine['debug'], 'wcprof/enabled', b'on')
        try:
            metrics, text, log = helpers.run('sort-profile-' + arm, root,
                ['api', 'call', 'gomod', 'at', '--path=.', 'own-files', '--glob=*.go'], engine)
        finally:
            helpers.request(engine['debug'], 'wcprof/enabled', b'off')
        try:
            files = json.loads(text)
        except json.JSONDecodeError:
            files = text.splitlines()
        assert metrics['cleanup_successful'] and files == expected
        lines = dump(arm).splitlines()
        header = json.loads(lines[0])
        counter = Counter()
        for line in lines[1:]:
            event = json.loads(line)
            if event['e'] == 'op':
                counter[(event.get('k', ''), header['strings'][event.get('c', 0)], event.get('o', ''))] += 1
        record = dict(arm=arm, profiling=True, excluded_from_benchmarks=True,
                      correct_files_and_order=True, event_count=header['event_count'],
                      dropped_events=header['dropped_events'], open_ops=len(header.get('open_ops', [])),
                      counts=[dict(kind=k, cls=c, outcome=o, count=n) for (k,c,o),n in counter.most_common()],
                      metrics=metrics, log=log)
        assert record['dropped_events'] == 0 and record['open_ops'] == 0
        records.append(record)
        (directory / 'counts.json').write_text(json.dumps(records, indent=2)+'\n')
        print(json.dumps(dict(arm=arm, calls=[c for c in record['counts'] if c['cls'].endswith('.ownFiles') or c['cls']=='Workspace.glob'])), flush=True)
finally:
    config.write_bytes(original_config)
    source.write_bytes(original_source)
    for name in names:
        (module / name).write_bytes(versions['candidate'][name])
