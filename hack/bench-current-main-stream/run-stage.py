#!/usr/bin/env python3
"""Sequential source-built correctness gate; never a latency benchmark."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'engine-source'
HELPER = Path('/tmp/dagger-rust-current-main-engine.QepteZyL/build.py')
CLI = Path('/tmp/dagger-cli-runewidth.lhU4UO4i/dagger-candidate')

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    label, pattern = sys.argv[1:]
    assert re.fullmatch('[a-z][a-z0-9-]*', label)
    assert sha(HELPER) == '6a56a60dfcefc3a5fe4460382b05dcf754cd7f8f632a862d1dd0018388b7ef4c'
    assert sha(CLI) == 'ff1ef25902a037b41e8b16372fcdb806c0cffdd1568a0b9ed75b4e1ef1631f51'
    spec = importlib.util.spec_from_file_location('base', HELPER)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    root = HERE / label
    root.mkdir()
    base.ROOT = root
    env = base.environment() | {'DAGGER_ENGINE': 'container://dagger-engine.rust-fresh-qeptezyl'}
    def read(*args):
        return subprocess.check_output(args, cwd=SOURCE, env=env, text=True).strip()
    assert read('git', 'rev-parse', 'HEAD') == '503d3410ef3df63fa6bc7a55c5c2453c4951c2c2'
    assert not (SOURCE/'.git/objects/info/alternates').exists()
    paths = read('rg', '--files', '--hidden', '-g', '!.git/**').splitlines()
    frozen = {p: sha(SOURCE/p) for p in sorted(paths)}
    patch = subprocess.check_output(['git', 'diff', '--binary'], cwd=SOURCE, env=env)
    (root/'source.patch').write_bytes(patch)
    argv = [str(CLI), 'api', 'call', 'engine-dev', 'test', '--pkg=./core/integration',
            '--run='+pattern, '--parallel=1', '--timeout=5m', '--count=1', '--test-verbose=true']
    record = dict(status='running', source=str(SOURCE), source_hashes=frozen,
                  patch_sha256=hashlib.sha256(patch).hexdigest(), controller_sha256=sha(__file__),
                  argv=argv, start_unix_ns=time.time_ns(), performance_benchmark=False)
    report = root/'stage.json'
    report.write_text(json.dumps(record, indent=2)+'\n')
    with (root/'engine-dev.log').open('xb') as output:
        result = subprocess.run(argv, cwd=SOURCE, env=env, stdout=output, stderr=subprocess.STDOUT)
    assert frozen == {p: sha(SOURCE/p) for p in sorted(paths)}, 'source drift during test'
    record.update(exit_code=result.returncode, end_unix_ns=time.time_ns(),
                  status='passed' if result.returncode == 0 else 'failed')
    report.write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({k: record[k] for k in ('status','exit_code','argv')}), flush=True)
    return result.returncode

if __name__ == '__main__':
    raise SystemExit(main())
