#!/usr/bin/env python3
"""Untimed full-tree readback for an explicitly named matrix fixture."""
import argparse
import json
import subprocess

import build
import matrix
from source_manifest import manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt', type=int, choices=range(1, 129))
    parser.add_argument('capture', choices=('edited', 'moved', 'mixed', 'reorg'))
    parser.add_argument('--compare-attempt', type=int)
    args = parser.parse_args()
    runtime = matrix.runtime_path(args.attempt)
    image = matrix.read_json(runtime / 'image.json')
    previous_owner = matrix.read_json(runtime / 'owner.json')
    matrix.inspect_owned(args.attempt, image, previous_owner)
    assert build.sha(runtime / 'dagger') == image['cli_sha256']
    output = runtime / ('verified-export-' + args.capture)
    receipt = runtime / ('export-' + args.capture + '.json')
    assert not output.exists() and not receipt.exists()
    expected = manifest(matrix.SOURCE)
    env = build.environment()
    for category in ('CONFIG', 'CACHE', 'DATA', 'STATE'):
        env['XDG_' + category + '_HOME'] = str(runtime / 'cli' / category.lower())
    name = matrix.engine_name(args.attempt)
    env['DAGGER_ENGINE'] = 'image+docker://' + image['tag'] + '?container=' + name + '&volume=' + name + '&cleanup=false'
    argv = [str(runtime / 'dagger'), 'api', 'query', '-M', '--doc', str(build.ROOT / 'import_export.graphql'),
            '--var-json', json.dumps({'path': str(matrix.SOURCE), 'output': str(output)})]
    with (runtime / ('export-' + args.capture + '.stdout')).open('xb') as stdout, (runtime / ('export-' + args.capture + '.stderr')).open('xb') as stderr:
        proc = subprocess.run(argv, env=env, cwd=matrix.SOURCE, stdin=subprocess.DEVNULL,
                              stdout=stdout, stderr=stderr, timeout=120)
    assert proc.returncode == 0, 'fixture readback failed; all evidence retained'
    actual = manifest(output)
    content = lambda rows: {name: {key: value for key, value in item.items() if key != 'mode'} for name, item in rows.items()}
    assert content(actual) == content(expected), 'export bytes/namespace/types/link targets differ'
    assert manifest(matrix.SOURCE) == expected, 'source changed during readback'
    if args.compare_attempt is not None:
        previous = matrix.read_json(matrix.runtime_path(args.compare_attempt) / receipt.name)
        assert previous['status'] == 'complete-tree-readback-passed'
        assert previous['source_manifest'] == expected and previous['export_manifest'] == actual
    matrix.inspect_owned(args.attempt, image, previous_owner)
    matrix.write_new(receipt, {'status': 'complete-tree-readback-passed', 'measured': False,
                              'capture': args.capture, 'source_manifest': expected, 'export_manifest': actual,
                              'argv': argv, 'controller_sha256': build.sha(__file__)})
    print(json.dumps({'attempt': args.attempt, 'capture': args.capture, 'entries': len(actual), 'status': 'readback-passed'}))


if __name__ == '__main__':
    main()
