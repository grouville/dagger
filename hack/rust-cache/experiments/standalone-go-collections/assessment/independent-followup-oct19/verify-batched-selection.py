"""Screen the standalone selection batch on packages containing main and tests."""
from pathlib import Path
import json
import statistics
import subprocess

from benchmark_helpers import engine_info, run

out = Path('/tmp/go-collection-upstream-review-oct19')
engine = engine_info('dagger-collection-standalone-main-oct19', 'tcp://127.0.0.1:16310', 'http://127.0.0.1:16130')
samples = []
for count in [1, 16]:
    arms = {}
    for arm, module in [('before', Path('/tmp/go-collection-clean-go-main')), ('candidate', out / 'go-batch-selection')]:
        root = out / f'batch-selection-fixed-{count}' / arm
        root.mkdir(parents=True)
        subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
        (root / 'go.mod').write_text('module example.com/selectionfixture\n\ngo 1.26.6\n')
        (root / 'dagger.toml').write_text('[modules.go]\nsource = "' + str(module) + '"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n')
        for index in range(count):
            package = root / f'pkg_{index:03d}'
            package.mkdir()
            (package / 'main.go').write_text('package main\nfunc main() {}\nfunc Value() int { return 42 }\n')
            (package / 'main_test.go').write_text('package main\nimport "testing"\nfunc TestValue(t *testing.T) { if Value() != 42 { t.Fatal("value") } }\n')
        source, test = root / 'pkg_000/main.go', root / 'pkg_000/main_test.go'
        arms[arm] = dict(root=root, source=source, test=test, source_bytes=source.read_bytes(), test_bytes=test.read_bytes())
    try:
        for pair in range(-2, 4):
            previous = None
            for arm in (['before', 'candidate'] if pair % 2 == 0 else ['candidate', 'before']):
                fixture = arms[arm]
                tag = f'{count}-{pair}'
                fixture['source'].write_bytes(fixture['source_bytes'] + f'\n// Source edit {tag}\n'.encode())
                fixture['test'].write_bytes(fixture['test_bytes'] + f'\n// Test edit {tag}\n'.encode() + (b'\nfunc TestAddedReview(t *testing.T) {}\n' if pair == -2 else b''))
                label = f'batch-selection-fixed-{count}-{pair}-{arm}'
                print(json.dumps(dict(event='listing-start', label=label)), flush=True)
                metrics, text, log = run(label, fixture['root'], ['check', '--module', 'go', '--check', 'test', '--list', '--all'], engine)
                lines = [line for line in text.splitlines() if line.startswith('go ')]
                names = [tuple(line.split()[1:3]) for line in lines]
                wanted = sorted([(f'pkg_{index:03d}', 'TestValue') for index in range(count)] + ([('pkg_000', 'TestAddedReview')] if pair == -2 else []))
                sample = dict(packages=count, pair=pair, arm=arm, warmup=pair < 0, rows=len(lines), correct_names=names == wanted, matching_rows=previous is None or previous == lines, fixed_configuration=True, fresh_cli=True, source_edit=True, test_edit=True, telemetry=True, profiling=False, log=log, **metrics)
                samples.append(sample)
                (out / 'batch-selection-fixed-samples.json').write_text(json.dumps(samples, indent=2) + '\n')
                print(json.dumps(sample), flush=True)
                assert sample['cleanup_successful'] and sample['correct_names'] and sample['matching_rows'], sample
                previous = lines
    finally:
        for fixture in arms.values():
            fixture['source'].write_bytes(fixture['source_bytes'])
            fixture['test'].write_bytes(fixture['test_bytes'])
summary = []
for count in [1, 16]:
    rows = [row for row in samples if row['packages'] == count and not row['warmup']]
    before = sorted([row for row in rows if row['arm'] == 'before'], key=lambda row: row['pair'])
    after = sorted([row for row in rows if row['arm'] == 'candidate'], key=lambda row: row['pair'])
    result = dict(packages=count, pairs=len(before), faster_pairs=sum(b['seconds'] < a['seconds'] for a, b in zip(before, after)), median_paired_saving=statistics.median(a['seconds'] - b['seconds'] for a, b in zip(before, after)))
    for metric in ['seconds', 'engine_cpu', 'allocated_bytes', 'allocations', 'peak_memory_current']:
        result['before_' + metric] = statistics.median(row[metric] for row in before)
        result['candidate_' + metric] = statistics.median(row[metric] for row in after)
    summary.append(result)
(out / 'batch-selection-fixed-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(dict(event='complete', summary=summary)), flush=True)
