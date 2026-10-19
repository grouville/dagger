"""Build the root-module row inventory independently of collection expansion."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

root = Path('/tmp/dagger-go-collection-current-main')
out = Path('/tmp/go-collection-upstream-review-oct19')
source = Path('/tmp/go-collection-clean-go-main/go.dang').read_text()
start = source.index('  let testMatches(')
pattern = re.search(r'pattern: `([^`]+)`', source[start:]).group(1)
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
nested = {str(Path(name).parent) for name in tracked if Path(name).name == 'go.mod' and name != 'go.mod'}
files = []
for name in tracked:
    path = Path(name)
    if not name.endswith('_test.go') or (root / name).is_symlink():
        continue
    if any(part == 'testdata' or part.startswith(('.', '_')) for part in path.parts):
        continue
    if any(str(parent) in nested for parent in path.parents):
        continue
    files.append(name)
result = subprocess.run(['rg', '--json', '--no-config', '--no-ignore', '--hidden', '--regexp', pattern, '--', *files],
                        cwd=root, capture_output=True, text=True, check=True)
rows = set()
for line in result.stdout.splitlines():
    event = json.loads(line)
    if event['type'] != 'match':
        continue
    data = event['data']
    file = data['path']['text']
    for match in data['submatches']:
        name = match['match']['text'].removeprefix('func ').split('(')[0]
        rows.add((str(Path(file).parent), name))
record = dict(root=str(root), tracked_files_only=True, root_module_only=True,
              source_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
              matcher=pattern, files=files, count=len(rows), rows=sorted(rows),
              file_sha256={name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files})
(out / 'root-test-inventory.json').write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
print(json.dumps(dict(files=len(files), rows=len(rows), source_revision=record['source_revision'])), flush=True)
