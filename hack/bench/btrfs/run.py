#!/usr/bin/env python3
"""Isolated materialization comparison; setup/mount is deliberately explicit.

Requires /bench/filesync.test, /fixtures/{original,edited,moved,mixed,reorg},
and a private mounted /btrfs inside the named container. No host scanning or
Dagger CLI claim: both arms receive the same pre-captured source manifest.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--container', required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--rounds', type=int, default=4)
p.add_argument('--profile', action='store_true')
args = p.parse_args()
args.out.mkdir()
run = args.out.name
assert run.replace('-', '').isalnum()
cases = [('cold-empty-store', 'original'), ('unchanged-forced', 'original'),
         ('one-file-edit', 'edited'), ('directory-move', 'moved'),
         ('mixed-diff', 'mixed'), ('broad-reorganization', 'reorg'),
         ('repeat-edited', 'edited')]
results = []

def command(*parts, **kwargs):
    return subprocess.run(['docker', 'exec', args.container, *parts], check=True, **kwargs)

for round_no in range(args.rounds):
    parent = ''
    for case, fixture in cases:
        arms = ['cas-ext4', 'cas-btrfs', 'btrfs-delta']
        if round_no % 2:
            arms.reverse()
        for arm in arms:
            root = {'cas-ext4': '/bench', 'cas-btrfs': '/btrfs-cas', 'btrfs-delta': '/btrfs'}[arm]
            base = f'{root}/{run}/round-{round_no}'
            output = f'{base}/{case}-{arm}'
            command('mkdir', '-p', base)
            if arm == 'btrfs-delta':
                env = {'BTRFS_BENCH_SOURCE': f'/fixtures/{fixture}', 'BTRFS_BENCH_OUT': output,
                       'BTRFS_BENCH_PARENT': parent, 'BTRFS_BENCH_CASE': case,
                       'BTRFS_BENCH_PROFILE': str(int(args.profile))}
                test = '^TestBtrfsDeltaMaterialize$'
            else:
                env = {'COMPOSEFS_BENCH_SOURCE': f'/fixtures/{fixture}', 'COMPOSEFS_BENCH_OUT': output,
                       'COMPOSEFS_BENCH_CACHE': f'{base}/cache-{arm}', 'COMPOSEFS_BENCH_CASE': case,
                       'COMPOSEFS_BENCH_ARM': 'cas', 'COMPOSEFS_BENCH_PROFILE': str(int(args.profile))}
                test = '^TestComposefsMaterialize$'
            cmd = ['docker', 'exec']
            for key, value in env.items():
                cmd += ['-e', f'{key}={value}']
            cmd += [args.container, '/bench/filesync.test', '-test.v', '-test.run', test]
            name = f'r{round_no}-{case}-{arm}'
            with (args.out / f'{name}.log').open('w') as log:
                subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
            value = json.loads(command('cat', f'{output}/result.json', capture_output=True, text=True).stdout)
            value.update(arm=arm, round=round_no, output=output)
            results.append(value)
            (args.out / 'results.json').write_text(json.dumps(results, indent=2))
            if args.profile:
                # docker cp does not see this container-private nested mount.
                with (args.out / f'{name}.wcprof.json').open('wb') as profile:
                    command('cat', f'{output}/wcprof.json', stdout=profile)
            if arm == 'btrfs-delta':
                parent = f'{output}/result'
            print(name, 'ready=', round(value['ms']['ready'], 2),
                  'read=', round(value['ms']['first_read_verify'], 2), flush=True)

rows = ['| State | CAS ext4 ready | CAS Btrfs ready | Btrfs delta ready |',
        '| --- | ---: | ---: | ---: |']
for case, _ in cases:
    medians = [statistics.median(v['ms']['ready'] for v in results if v['case'] == case and v['arm'] == arm)
               for arm in ['cas-ext4', 'cas-btrfs', 'btrfs-delta']]
    rows.append('| ' + case + ' | ' + ' | '.join(f'{m:.2f}' for m in medians) + ' |')
(args.out / 'RESULTS.md').write_text('\n'.join(rows) + '\n')
