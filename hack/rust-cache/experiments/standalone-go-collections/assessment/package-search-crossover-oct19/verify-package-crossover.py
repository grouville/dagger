"""Validate discovery gains without assigning each version a different host root."""
from pathlib import Path
import hashlib
import json
import statistics
import subprocess

from benchmark_helpers import engine_info, run

out = Path('/tmp/go-collection-upstream-review-oct19')
assert all(r['cleanup_successful'] for r in json.loads((out / 'scoped-resume-checks.json').read_text()))
engine = engine_info('dagger-collection-standalone-main-oct19', 'tcp://127.0.0.1:16310', 'http://127.0.0.1:16130')
main = Path('/tmp/go-collection-clean-go-main')
candidate = out / 'go-package-workspace'
fingerprint = hashlib.sha256((candidate / 'go.dang').read_bytes()).hexdigest()
(out / 'crossover-source.patch').write_bytes(subprocess.check_output([
    'git', '-C', str(candidate), 'diff', '334136faaa1cd36ac26dfdc648eda907ce99c063',
    '--', 'go.dang', '.dagger/modules/go-dev/main.dang',
]))
records = []


def summarize():
    summary = []
    for phase in dict.fromkeys(r['phase'] for r in records):
        rows = [r for r in records if r['phase'] == phase and not r['warmup']]
        before = sorted((r for r in rows if r['arm'] == 'before'), key=lambda r: r['pair'])
        after = sorted((r for r in rows if r['arm'] == 'after'), key=lambda r: r['pair'])
        if not before or len(before) != len(after):
            continue
        row = dict(phase=phase, packages=before[0]['packages'], files=before[0]['files'],
                   pairs=len(before), faster_pairs=sum(a['seconds'] < b['seconds'] for b, a in zip(before, after)),
                   median_paired_saving=statistics.median(b['seconds'] - a['seconds'] for b, a in zip(before, after)))
        for metric in ['seconds', 'engine_cpu', 'allocated_bytes', 'allocations']:
            row['before_' + metric] = statistics.median(r[metric] for r in before)
            row['after_' + metric] = statistics.median(r[metric] for r in after)
        summary.append(row)
    (out / 'crossover-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


for phase, packages, files in [('same-code', 16, 1), ('many-packages', 16, 1), ('many-files', 1, 16), ('one-file', 1, 1)]:
    root = out / ('crossover-' + phase)
    root.mkdir()
    subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
    (root / 'go.mod').write_text('module example.com/crossover\n\ngo 1.26.6\n')
    config = ''
    for arm in ['before', 'after']:
        module = main if arm == 'before' or phase == 'same-code' else candidate
        config += f'[modules.{arm}]\nsource = "{module}"\n[modules.{arm}.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["**"]\n\n'
    (root / 'dagger.toml').write_text(config)
    expected = []
    for package_index in range(packages):
        package = root / f'pkg_{package_index:03d}'
        package.mkdir()
        (package / 'value.go').write_text('package fixture\nfunc Value() int { return 42 }\n')
        for file_index in range(files):
            text = 'package fixture\nimport "testing"\n'
            for test_index in range(8):
                name = f'TestCase{file_index * 8 + test_index:03d}'
                text += f'func {name}(t *testing.T) {{ if Value()!=42 {{ t.Fatal("wrong value") }} }}\n'
                expected.append((f'pkg_{package_index:03d}', name))
            (package / f'value_{file_index:03d}_test.go').write_text(text)
    source = root / 'pkg_000/value.go'
    test = root / 'pkg_000/value_000_test.go'
    original_source, original_test = source.read_bytes(), test.read_bytes()
    try:
        for pair in range(-2, 6):
            prior_rows = None
            for position, arm in enumerate(['before', 'after'] if pair % 2 == 0 else ['after', 'before']):
                assert (root / 'dagger.toml').read_text() == config
                assert hashlib.sha256((candidate / 'go.dang').read_bytes()).hexdigest() == fingerprint
                renamed = f'TestCase000Edit{max(pair, 0)}'
                edited = original_test if pair < 0 else original_test.replace(b'func TestCase000(', f'func {renamed}('.encode(), 1)
                if pair == -2:
                    edited += b'\nfunc TestAddedCrossover(t *testing.T) {}\n'
                # Distinct comments force a file edit even for the second command in a pair.
                comment = f'\n// Crossover {phase} pair {pair} position {position}\n'.encode()
                source.write_bytes(original_source + comment)
                test.write_bytes(edited + comment)
                label = f'crossover-{phase}-{pair}-{arm}'
                print(json.dumps(dict(event='start', label=label)), flush=True)
                metrics, text, log = run(label, root, ['check', '--module', arm, '--check', 'test', '--list', '--all'], engine)
                lines = [line.split() for line in text.splitlines() if line.split() and line.split()[0] == arm]
                names = [tuple(line[1:3]) for line in lines]
                wanted = sorted((pkg, renamed if pair >= 0 and pkg == 'pkg_000' and name == 'TestCase000' else name) for pkg, name in expected)
                if pair == -2:
                    wanted = sorted([*wanted, ('pkg_000', 'TestAddedCrossover')])
                normalized = [line[1:] for line in lines]
                record = dict(phase=phase, packages=packages, files=files, pair=pair, arm=arm,
                              warmup=pair < 0, names_correct=names == wanted, rows=len(lines),
                              same_rows=prior_rows is None or normalized == prior_rows,
                              same_workspace_for_both_arms=True, fixed_configuration=True,
                              test_name_edit=pair >= 0, fresh_cli=True, telemetry=True, profiling=False,
                              candidate_go_sha256=fingerprint, log=log, **metrics)
                records.append(record)
                (out / 'crossover-samples.json').write_text(json.dumps(records, indent=2) + '\n')
                print(json.dumps(record), flush=True)
                assert record['cleanup_successful'] and record['names_correct'] and record['same_rows'], record
                prior_rows = normalized
                summarize()
    finally:
        source.write_bytes(original_source)
        test.write_bytes(original_test)
    print(json.dumps(dict(event='case-complete', summary=summarize()[-1])), flush=True)
(out / 'crossover-complete.json').write_text(json.dumps(dict(complete=True, commands=len(records)), indent=2) + '\n')
