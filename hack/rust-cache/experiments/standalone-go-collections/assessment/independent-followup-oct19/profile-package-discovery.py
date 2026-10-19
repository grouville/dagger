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
engine = engine_info('dagger-collection-standalone-main-oct19', 'tcp://127.0.0.1:16310', 'http://127.0.0.1:16130')
assert json.loads((out / 'package-discovery-complete.json').read_text())['complete']
reporter = Path('/tmp/go-collection-clean-branches/real-repository/wcprof-report')
directory = out / 'package-discovery-wcprof'
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
for arm in ['before', 'candidate']:
    root = out / 'package-discovery-16-packages-1-files' / arm
    source, test = root / 'pkg_000/value.go', root / 'pkg_000/value_000_test.go'
    original_source, original_test = source.read_bytes(), test.read_bytes()
    try:
        source.write_bytes(original_source + b'\n// Profile source edit\n')
        test.write_bytes(original_test + b'\n// Profile test edit\n')
        request(engine['debug'], 'wcprof/enabled', b'on')
        try:
            metrics, text, log = run('package-discovery-profile-' + arm, root, ['check', '--module', 'go', '--check', 'test', '--list', '--all'], engine)
        finally:
            request(engine['debug'], 'wcprof/enabled', b'off')
        assert metrics['cleanup_successful'], log
        assert len([line for line in text.splitlines() if line.startswith('go ')]) == 128
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
