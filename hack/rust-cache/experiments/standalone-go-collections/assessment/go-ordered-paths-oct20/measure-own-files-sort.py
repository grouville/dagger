"""Time the real owned-file command, holding engine, CLI and module path fixed."""
from pathlib import Path
import hashlib
import json
import statistics
import subprocess
import sys
import time

out = Path('/tmp/go-listing-current-main-oct20')
sys.path.insert(0, '/tmp/go-collection-upstream-review-oct19')
import config_dagql_benchmark_helpers as helpers
helpers.out = out
helpers.cli = out / 'main-cli'
info = json.loads((out / 'engine.json').read_text())
engine = helpers.engine_info(info['name'], info['runner'], info['debug'])
root = Path('/tmp/dagger-go-collection-current-main')
config, source = root / 'dagger.toml', root / 'dagql/types.go'
original_config, original_source = config.read_bytes(), source.read_bytes()
module = out / 'go-sorted-inputs'
names = ['go.dang', 'gomod/main.dang']
versions = {arm: {name: (out / ('go-main' if arm == 'main' else 'go-sorted-inputs') / name).read_bytes()
                   for name in names} for arm in ['main', 'candidate']}
assert all(versions['main'][name] != versions['candidate'][name] for name in names)
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
nested = [str(Path(name).parent) for name in tracked if name.endswith('/go.mod')]
expected = sorted([name for name in tracked if name.endswith('.go')
                   and not any(part == 'testdata' or part.startswith(('.', '_')) for part in name.split('/'))
                   and not any(name.startswith(path + '/') for path in nested)], key=lambda name: name.encode())
assert len(expected) > 1000
(out / 'owned-file-inventory.json').write_text(json.dumps(dict(source_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(), files=expected), indent=2)+'\n')
records = []
try:
    config.write_text('[modules.gomod]\nsource = "' + str(module / 'gomod') + '"\n')
    for pair in range(-1, 4):
        for arm in (['main', 'candidate'] if pair % 2 == 0 else ['candidate', 'main']):
            for name in names:
                (module / name).write_bytes(versions[arm][name])
            source.write_bytes(original_source + ('\n// Owned-file sort comparison ' + str(time.time_ns()) + '\n').encode())
            label = 'sort-own-files-' + str(pair) + '-' + arm
            print(json.dumps(dict(event='start', label=label, expected_files=len(expected))), flush=True)
            metrics, text, log = helpers.run(label, root,
                ['api', 'call', 'gomod', 'at', '--path=.', 'own-files', '--glob=*.go'], engine)
            try:
                files = json.loads(text)
            except json.JSONDecodeError:
                files = text.splitlines()
            correct = files == expected
            record = dict(pair=pair, arm=arm, warmup=pair < 0, correct_files_and_order=correct,
                          expected_files=len(expected), actual_files=len(files),
                          source_and_config_fixed=True, fresh_cli=True, source_edit=True,
                          telemetry=True, profiling=False, log=log,
                          module_hashes={name: hashlib.sha256(versions[arm][name]).hexdigest() for name in names},
                          **metrics)
            records.append(record)
            (out / 'sort-own-files-samples.json').write_text(json.dumps(records, indent=2)+'\n')
            print(json.dumps(record), flush=True)
            assert record['cleanup_successful'] and correct, record
finally:
    config.write_bytes(original_config)
    source.write_bytes(original_source)
    for name in names:
        (module / name).write_bytes(versions['candidate'][name])
summary = dict(pairs=4, faster_pairs=sum(next(r['seconds'] for r in records if r['pair']==pair and r['arm']=='candidate') <
                                       next(r['seconds'] for r in records if r['pair']==pair and r['arm']=='main') for pair in range(4)))
for arm in ['main', 'candidate']:
    selected = [r for r in records if r['arm']==arm and not r['warmup']]
    summary[arm] = {key: statistics.median(r[key] for r in selected)
                    for key in ['seconds', 'engine_cpu', 'allocated_bytes', 'allocations', 'peak_memory_current']}
(out / 'sort-own-files-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(summary), flush=True)
