"""Compare ownership reuse on upstream main at a realistic packages/modules ratio."""
from pathlib import Path
import hashlib
import json
import statistics
import subprocess

from benchmark_helpers import engine_info, run

out = Path('/tmp/go-collection-upstream-review-oct19')
engine = engine_info('dagger-collection-standalone-main-oct19', 'tcp://127.0.0.1:16310', 'http://127.0.0.1:16130')
main = Path('/tmp/go-collection-clean-go-main')
candidate = out / 'go-ownership'
production = ['go.dang', 'gomod/main.dang']
fingerprints = {name: hashlib.sha256((candidate / name).read_bytes()).hexdigest() for name in production}
(out / 'ownership-confirm-source.patch').write_bytes(subprocess.check_output([
    'git', '-C', str(candidate), 'diff', '--', *production, '.dagger/modules/go-dev/main.dang',
]))
records = []


def summarize():
    summary = []
    for phase in dict.fromkeys(row['phase'] for row in records):
        rows = [row for row in records if row['phase'] == phase and not row['warmup']]
        before = sorted((row for row in rows if row['arm'] == 'before'), key=lambda row: row['pair'])
        after = sorted((row for row in rows if row['arm'] == 'after'), key=lambda row: row['pair'])
        if not before or len(before) != len(after):
            continue
        item = dict(phase=phase, modules=before[0]['modules'], packages=before[0]['packages'],
                    pairs=len(before), faster_pairs=sum(a['seconds'] < b['seconds'] for b, a in zip(before, after)),
                    median_paired_saving=statistics.median(b['seconds'] - a['seconds'] for b, a in zip(before, after)))
        for key in ['seconds', 'engine_cpu', 'allocated_bytes', 'allocations', 'peak_memory_current']:
            item['before_' + key] = statistics.median(row[key] for row in before)
            item['after_' + key] = statistics.median(row[key] for row in after)
        summary.append(item)
    (out / 'ownership-confirm-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


for phase, modules, packages_per_module, pairs in [('many-packages', 8, 8, 4), ('same-code', 8, 8, 2), ('one-package', 1, 1, 4)]:
    root = out / ('ownership-confirm-' + phase)
    root.mkdir()
    subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
    config = ''
    for arm in ['before', 'after']:
        module = main if arm == 'before' or phase == 'same-code' else candidate
        config += f'[modules.{arm}]\nsource = "{module}"\n[modules.{arm}.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n\n'
    (root / 'dagger.toml').write_text(config)
    expected = []
    for module_index in range(modules):
        module = root / f'mod_{module_index:03d}'
        module.mkdir()
        (module / 'go.mod').write_text(f'module example.com/ownership/mod{module_index}\n\ngo 1.26.6\n')
        for package_index in range(packages_per_module):
            package = module / f'pkg_{package_index:03d}'
            package.mkdir()
            (package / 'value.go').write_text('package fixture\nfunc Value() int { return 42 }\n')
            (package / 'value_test.go').write_text('package fixture\nimport "testing"\nfunc TestValue(t *testing.T) { if Value()!=42 {t.Fatal("value")} }\n')
            expected.append((f'mod_{module_index:03d}/pkg_{package_index:03d}', 'TestValue'))
    source = root / 'mod_000/pkg_000/value.go'
    test = root / 'mod_000/pkg_000/value_test.go'
    original_source, original_test = source.read_bytes(), test.read_bytes()
    try:
        for pair in range(-2, pairs):
            previous = None
            for position, arm in enumerate(['before', 'after'] if pair % 2 == 0 else ['after', 'before']):
                assert (root / 'dagger.toml').read_text() == config
                assert all(hashlib.sha256((candidate / name).read_bytes()).hexdigest() == fingerprints[name] for name in production)
                renamed = f'TestValueEdit{max(pair, 0)}'
                edited_test = original_test if pair < 0 else original_test.replace(b'func TestValue(', f'func {renamed}('.encode(), 1)
                if pair == -2:
                    edited_test += b'\nfunc TestAddedOwnership(t *testing.T) {}\n'
                comment = f'\n// Ownership {phase} pair {pair} position {position}\n'.encode()
                source.write_bytes(original_source + comment)
                test.write_bytes(edited_test + comment)
                label = f'ownership-confirm-{phase}-{pair}-{arm}'
                print(json.dumps(dict(event='start', label=label)), flush=True)
                metrics, text, log = run(label, root, ['check', '--module', arm, '--check', 'test', '--list', '--all'], engine)
                lines = [line.split() for line in text.splitlines() if line.split() and line.split()[0] == arm]
                names = [tuple(line[1:3]) for line in lines]
                wanted = sorted((pkg, renamed if pair >= 0 and pkg == 'mod_000/pkg_000' else name) for pkg, name in expected)
                if pair == -2:
                    wanted = sorted([*wanted, ('mod_000/pkg_000', 'TestAddedOwnership')])
                normalized = [line[1:] for line in lines]
                record = dict(phase=phase, modules=modules, packages=modules * packages_per_module,
                              pair=pair, arm=arm, warmup=pair < 0, rows=len(names),
                              correct_names=names == wanted, same_rows=previous is None or normalized == previous,
                              fixed_configuration=True, same_workspace=True, fresh_cli=True,
                              source_edit=True, test_edit=True, test_name_edit=pair >= 0,
                              telemetry=True, profiling=False, production_sha256=fingerprints, log=log, **metrics)
                records.append(record)
                (out / 'ownership-confirm-samples.json').write_text(json.dumps(records, indent=2) + '\n')
                print(json.dumps(record), flush=True)
                assert record['cleanup_successful'] and record['correct_names'] and record['same_rows'], record
                previous = normalized
                summarize()
    finally:
        source.write_bytes(original_source)
        test.write_bytes(original_test)
    print(json.dumps(dict(event='case-complete', summary=summarize()[-1])), flush=True)
(out / 'ownership-confirm-complete.json').write_text(json.dumps(dict(complete=True, commands=len(records)), indent=2) + '\n')
