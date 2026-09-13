#!/usr/bin/env python3
"""Reconstruct only the patched files in a new owned tree; verify exact hashes.

No source checkout is edited, no network/build is started and no files are deleted.
The temporary reproduction tree is retained for inspection.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control-dagger', required=True, type=Path)
    parser.add_argument('--control-containerd', required=True, type=Path)
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent
    manifest = json.loads((evidence / 'source-manifest.json').read_text())
    dagger = args.control_dagger.resolve(strict=True)
    containerd = args.control_containerd.resolve(strict=True)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=dagger, text=True).strip()
    assert actual == manifest['parent'], 'use the recorded Dagger control revision'
    root = Path(tempfile.mkdtemp(prefix='dagger-current-stream-patch-check-'))
    print(root, flush=True)
    prefix = 'internal/bench-image-stream/containerd/'
    records = []
    for record in manifest['files']:
        path = record['path']
        relative = Path(path[len(prefix):] if path.startswith(prefix) else path)
        assert not relative.is_absolute() and '..' not in relative.parts
        bucket = 'containerd' if path.startswith(prefix) else 'engine'
        source = (containerd if bucket == 'containerd' else dagger) / relative
        target = root / bucket / relative
        if record['before'] is not None:
            assert source.is_file() and sha(source) == record['before'], str(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        else:
            assert not source.exists(), str(source)
        records.append((target, record['after']))
    for bucket in ('engine', 'containerd'):
        directory = root / bucket
        directory.mkdir(exist_ok=True)
        patch = evidence / (bucket + '.patch')
        subprocess.run(['git', 'apply', '--check', '--whitespace=error-all', str(patch)], cwd=directory, check=True)
        subprocess.run(['git', 'apply', '--whitespace=error-all', str(patch)], cwd=directory, check=True)
    for target, expected in records:
        assert sha(target) == expected, str(target)
    stages = json.loads((evidence / 'close-order-validation.json').read_text())
    before, after = stages['gated-before'], stages['gated-after']
    assert before['exit_code'] == 1 and after['exit_code'] == 0
    assert before['argv'] == after['argv']
    changed = [key for key in before['source_hashes']
               if before['source_hashes'][key] != after['source_hashes'][key]]
    dependency_path = prefix + 'core/diff/apply/apply.go'
    assert changed == [dependency_path]
    patch = evidence / 'close-order-only.patch'
    directory = root / 'containerd'
    target = directory / 'core/diff/apply/apply.go'
    subprocess.run(['git', 'apply', '--reverse', str(patch)], cwd=directory, check=True)
    assert sha(target) == before['source_hashes'][dependency_path]
    subprocess.run(['git', 'apply', str(patch)], cwd=directory, check=True)
    assert sha(target) == after['source_hashes'][dependency_path]
    print(json.dumps({'status': 'passed', 'files': len(records),
                     'close_order_negative_positive_reconstruction': True,
                     'root': str(root)}))


if __name__ == '__main__':
    main()
