"""Capture work counts after timing; do not use these runs as timing samples."""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import subprocess
import urllib.error
import urllib.request

from benchmark_helpers import engine_info, request, run

out = Path('/tmp/go-collection-upstream-review-oct19')
engine = engine_info('dagger-go-listing-controlled-before-oct19', 'tcp://127.0.0.1:32840', 'http://127.0.0.1:32841')
assert json.loads((out / 'ownership-controlled-complete.json').read_text())['complete']
reporter = Path('/tmp/go-collection-clean-branches/real-repository/wcprof-report')
directory = out / 'ownership-controlled-wcprof'
directory.mkdir()

def dump(name):
    path = directory / (name + '.ndjson.gz')
    try:
        with urllib.request.urlopen(engine['debug'] + '/debug/wcprof/dump', timeout=60) as response, gzip.open(path, 'wb') as target:
            shutil.copyfileobj(response, target)
    except urllib.error.HTTPError as error:
        if name != 'prior-buffer' or error.code != 503:
            raise
        path.unlink(missing_ok=True)
        return None
    return path

# Preserve and flush any older diagnostic capture before enabling this one.
dump('prior-buffer')
records = []
for arm in ['first', 'second', 'third']:
    root = out / 'ownership-controlled-many-packages'
    config = root / 'dagger.toml'
    original_config = config.read_bytes()
    source, test = root / 'mod_000/pkg_000/value.go', root / 'mod_000/pkg_000/value_test.go'
    original_source, original_test = source.read_bytes(), test.read_bytes()
    try:
        config.write_text('[modules.go]\nsource = \"/tmp/go-collection-clean-go-main\"\n[modules.go.settings]\nversion = \"1.26.6\"\ngoflags = \"-p=8\"\ntest = [\"**\"]\n')
        source.write_bytes(original_source + ('\n// Profile source edit ' + arm + '\n').encode())
        assert original_test.count(b'func TestValue(') == 1
        renamed = 'TestValueProfile' + str(__import__('time').time_ns())
        test.write_bytes(original_test.replace(b'func TestValue(', ('func ' + renamed + '(').encode(), 1) + b'\n// Profile test edit\n')
        request(engine['debug'], 'wcprof/enabled', b'on')
        try:
            metrics, text, log = run('ownership-controlled-profile-' + arm, root, ['check', '--module', 'go', '--check', 'test', '--list', '--all'], engine)
        finally:
            request(engine['debug'], 'wcprof/enabled', b'off')
        assert metrics['cleanup_successful'], log
        lines = [line for line in text.splitlines() if line.split() and line.split()[0] == 'go']
        assert len(lines) == 64
        assert any(line.split()[1:3] == ['mod_000/pkg_000', renamed] for line in lines)
        path = dump(arm)
        with gzip.open(path, 'rt') as stream:
            header = json.loads(next(stream))
            counts = Counter()
            outcomes = Counter()
            for line in stream:
                event = json.loads(line)
                if event['e'] == 'op':
                    key = (event.get('k', ''), header['strings'][event.get('c', 0)])
                    counts[key] += 1
                    outcomes[(*key, event.get('o', ''))] += 1
        record = dict(arm=arm, profiling=True, excluded_from_timing=True, log=log, **metrics,
                      dump=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      event_count=header['event_count'], dropped_events=header['dropped_events'], open_ops=len(header.get('open_ops', [])),
                      counts=[dict(kind=k, cls=c, count=n) for (k, c), n in counts.most_common()],
                      outcomes=[dict(kind=k, cls=c, outcome=o, count=n) for (k, c, o), n in outcomes.most_common()])
        records.append(record)
        assert record['dropped_events'] == 0 and record['open_ops'] == 0
        (directory / 'counts.json').write_text(json.dumps(records, indent=2) + '\n')
        raw = directory / (arm + '.ndjson')
        with gzip.open(path, 'rb') as stream, raw.open('wb') as target:
            shutil.copyfileobj(stream, target)
        for view in ['summary', 'classes', 'critpath']:
            with (directory / (arm + '-' + view + '.txt')).open('w') as report:
                subprocess.run([str(reporter), '-view', view, '-top', '50', '-limit', '180', str(raw)], stdout=report, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({key: record[key] for key in ['arm', 'event_count', 'dropped_events', 'open_ops', 'sha256']}), flush=True)
    finally:
        source.write_bytes(original_source)
        test.write_bytes(original_test)
        config.write_bytes(original_config)
