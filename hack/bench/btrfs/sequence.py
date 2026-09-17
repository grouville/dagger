#!/usr/bin/env python3
"""Retain a long snapshot history; every step verifies its predecessor too."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--container', required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--edits', type=int, default=128)
args = p.parse_args()
args.out.mkdir()
source = args.out / 'source'
shutil.copytree(args.fixture, source, symlinks=True)
run = args.out.name
assert run.replace('-', '').isalnum()
files = sorted(source.glob('crates/**/*.rs'))
original = {path: path.read_bytes() for path in files[:args.edits]}
parent = ''
results = []
for i in range(args.edits + 1):
    if i:
        # Repeated edits to one file, followed by edits across distinct paths.
        path = files[0] if i <= args.edits // 2 else files[i - args.edits // 2]
        path.write_bytes(original[path] + f'\n// delta sequence {i}\n'.encode())
    output = f'/btrfs/{run}/step-{i:03d}'
    subprocess.run(['docker', 'exec', args.container, 'mkdir', '-p', f'/btrfs/{run}'], check=True)
    env = {'BTRFS_BENCH_SOURCE': f'/bench/{run}/source', 'BTRFS_BENCH_OUT': output,
           'BTRFS_BENCH_PARENT': parent, 'BTRFS_BENCH_CASE': f'step-{i}', 'BTRFS_BENCH_PROFILE': '0'}
    cmd = ['docker', 'exec']
    for k, v in env.items():
        cmd += ['-e', f'{k}={v}']
    cmd += [args.container, '/bench/filesync.test', '-test.run', '^TestBtrfsDeltaMaterialize$', '-test.v']
    with (args.out / f'step-{i:03d}.log').open('w') as log:
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
    value = json.loads(subprocess.run(['docker', 'exec', args.container, 'cat', f'{output}/result.json'],
                                     check=True, capture_output=True, text=True).stdout)
    results.append(value)
    (args.out / 'results.json').write_text(json.dumps(results, indent=2))
    parent = f'{output}/result'
    print(i, round(value['ms']['ready'], 2), 'ms; files written', value['written'], flush=True)
