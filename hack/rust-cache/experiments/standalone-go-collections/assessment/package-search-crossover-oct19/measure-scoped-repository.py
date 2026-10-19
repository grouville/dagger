"""One full-repository listing, preserving its source and installed-module config."""
from pathlib import Path
import json
import subprocess

out = Path('/tmp/go-collection-upstream-review-oct19')
source = Path('/tmp/dagger-go-collection-current-main')
evidence = Path('/tmp/go-collection-clean-branches/real-repository')
label = 'package-scoped-repository-oct19'
config = source / 'dagger.toml'
original = config.read_bytes()
expected = {tuple(row) for row in json.loads((out / 'root-test-inventory.json').read_text())['rows']}
assert len(expected) == 4482
expected.add(('dagql', 'TestCollectionReviewAdded'))
assert b'/tmp/go-collection-clean-go-main' in original
try:
    config.write_bytes(original.replace(b'/tmp/go-collection-clean-go-main', bytes(str(out / 'go-package-workspace'), 'utf-8')))
    result = subprocess.run(['python3', '-u', str(evidence / 'measure.py'), '--label', label, '--add-test', '--timeout', '240'])
    report = json.loads((evidence / label / 'result.json').read_text())
    lines = [line.split() for line in (evidence / label / 'stdout').read_text().splitlines() if line.startswith('go ')]
    names = [tuple(line[1:3]) for line in lines]
    report.update(expected_rows=len(expected), correct_names=set(names) == expected,
                  correct_order=names == sorted(expected), warm_engine=True,
                  source_module=str(out / 'go-package-workspace'), verification_inventory=str(out / 'root-test-inventory.json'))
    (out / 'scoped-full-repository-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
    assert result.returncode == 0 and report['correct_names'] and report['correct_order'], report
finally:
    config.write_bytes(original)
