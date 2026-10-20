"""Screen a root-path identity change using the complete collection command."""
from pathlib import Path
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time

out = Path('/tmp/go-listing-current-main-oct20')
sys.path.insert(0, '/tmp/go-collection-upstream-review-oct19')
import config_dagql_benchmark_helpers as helpers

parser = argparse.ArgumentParser()
parser.add_argument('--packages', type=int, default=16)
parser.add_argument('--pairs', type=int, default=2)
parser.add_argument('--nested', action='store_true')
args = parser.parse_args()
label_prefix = 'root-path-' + ('nested-' if args.nested else 'root-') + str(args.packages)
helpers.out = out
helpers.cli = out / 'main-cli'
info = json.loads((out / 'engine.json').read_text())
engine = helpers.engine_info(info['name'], info['runner'], info['debug'])
module = out / 'go-root-path'
production = module / 'go.dang'
versions = {'main': (out / 'go-main/go.dang').read_bytes(),
            'candidate': production.read_bytes()}
assert versions['main'] != versions['candidate']
root = out / (label_prefix + '-fixture')
root.mkdir()
subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
(root / 'dagger.toml').write_text('[modules.go]\nsource = "' + str(module) + '"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n')
module_root = root / 'nested' if args.nested else root
module_root.mkdir(exist_ok=True)
(module_root / 'go.mod').write_text('module example.com/rootpaths\n\ngo 1.26.6\n')
for index in range(args.packages):
    package = module_root / ('pkg_' + str(index).zfill(3))
    package.mkdir()
    (package / 'value.go').write_text('package fixture\nfunc Value() int { return 42 }\n')
    (package / 'value_test.go').write_text('package fixture\nimport "testing"\nfunc TestValue(t *testing.T) { if Value()!=42 {t.Fatal("value")} }\n')
source, test = module_root / 'pkg_000/value.go', module_root / 'pkg_000/value_test.go'
original_source, original_test = source.read_bytes(), test.read_bytes()
records = []
try:
    for pair in range(-1, args.pairs):
        for arm in (['main', 'candidate'] if pair % 2 == 0 else ['candidate', 'main']):
            production.write_bytes(versions[arm])
            marker = 'TestEdited' + str(time.time_ns())
            source.write_bytes(original_source + ('\n// Source edit ' + marker + '\n').encode())
            test.write_bytes(original_test.replace(b'func TestValue(', ('func ' + marker + '(').encode(), 1))
            label = label_prefix + '-' + str(pair) + '-' + arm
            print(json.dumps(dict(event='start', label=label)), flush=True)
            metrics, text, log = helpers.run(label, root,
                ['check', '--module', 'go', '--check', 'test', '--list', '--all'], engine)
            rows = [line.split()[1:3] for line in text.splitlines() if line.split() and line.split()[0] == 'go']
            prefix = 'nested/' if args.nested else ''
            expected = [[prefix + 'pkg_' + str(index).zfill(3), marker if index == 0 else 'TestValue'] for index in range(args.packages)]
            record = dict(pair=pair, arm=arm, packages=args.packages, nested=args.nested,
                          warmup=pair < 0, correct_names_and_order=rows == expected,
                          expected_rows=len(expected), actual_rows=len(rows),
                          fresh_cli=True, source_edit=True, test_edit=True,
                          telemetry=True, profiling=False, fixed_module_path=True,
                          module_sha256=hashlib.sha256(versions[arm]).hexdigest(),
                          log=log, **metrics)
            records.append(record)
            (out / (label_prefix + '-samples.json')).write_text(json.dumps(records, indent=2)+'\n')
            print(json.dumps(record), flush=True)
            assert record['correct_names_and_order'] and record['cleanup_successful'], record
finally:
    source.write_bytes(original_source)
    test.write_bytes(original_test)
    production.write_bytes(versions['candidate'])
summary = dict(pairs=args.pairs, packages=args.packages, nested=args.nested)
for arm in ['main', 'candidate']:
    selected = [record for record in records if record['arm'] == arm and not record['warmup']]
    summary[arm] = {key: statistics.median(row[key] for row in selected)
                    for key in ['seconds', 'engine_cpu', 'allocated_bytes', 'allocations', 'peak_memory_current']}
summary['faster_pairs'] = sum(next(r['seconds'] for r in records if r['pair'] == pair and r['arm'] == 'candidate') <
                             next(r['seconds'] for r in records if r['pair'] == pair and r['arm'] == 'main') for pair in range(args.pairs))
(out / (label_prefix + '-summary.json')).write_text(json.dumps(summary, indent=2)+'\n')
print(json.dumps(dict(event='complete', summary=summary)), flush=True)
