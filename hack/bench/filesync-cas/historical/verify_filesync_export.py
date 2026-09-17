#!/usr/bin/env python3
"""Full materialized-tree readback AFTER timed flows; not a benchmark sample."""
import argparse
import json
import subprocess

import build
from source_manifest import manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt', type=int, choices=range(1, 129))
    parser.add_argument('--compare-attempt', type=int)
    parser.add_argument('--capture', choices=('moved',), help='Keep a second, separately named moved-tree readback')
    args = parser.parse_args()
    runtime = build.ROOT / f'runtime-r{args.attempt}'
    source = build.ROOT / 'ruff'
    suffix = '-moved' if args.capture == 'moved' else ''
    output = runtime / ('verified-export' + suffix)
    receipt_path = runtime / ('export' + suffix + '.json')
    assert not output.exists() and not receipt_path.exists()
    assert (runtime / 'leaf1-exact/receipt.json').exists()
    if args.capture == 'moved':
        assert (runtime / 'ab1-exact/receipt.json').exists()
    expected = manifest(source)
    image = json.loads((runtime / 'image.json').read_text())
    assert build.sha(runtime / 'dagger') == image['cli_sha256']
    env = build.environment()
    for category in ('CONFIG', 'CACHE', 'DATA', 'STATE'):
        env['XDG_' + category + '_HOME'] = str(runtime / 'cli' / category.lower())
    name = f'dagger-storage-host-efb1uyhh-r{args.attempt}-engine'
    env['DAGGER_ENGINE'] = 'image+docker://' + image['tag'] + '?container=' + name + '&volume=' + name + '&cleanup=false'
    argv = [str(runtime / 'dagger'), 'api', 'query', '-M', '--doc', str(build.ROOT / 'import_export.graphql'),
            '--var-json', json.dumps({'path': str(source), 'output': str(output)})]
    with (runtime / ('export' + suffix + '.stdout')).open('xb') as stdout, (runtime / ('export' + suffix + '.stderr')).open('xb') as stderr:
        proc = subprocess.run(argv, cwd=source, env=env, stdin=subprocess.DEVNULL, stdout=stdout,
                              stderr=stderr, timeout=120)
    assert proc.returncode == 0, 'export failed; diagnostic retained'
    actual = manifest(output)
    # Export's host mode policy is separate from snapshot modes. Require all
    # file bytes/types/link targets against source, then full main/CAS mode parity.
    def bytes_and_types(rows):
        return {name: {key: value for key, value in item.items() if key != 'mode'} for name, item in rows.items()}
    assert bytes_and_types(actual) == bytes_and_types(expected), 'materialized tree differs from source'
    assert manifest(source) == expected, 'source changed during export'
    if args.compare_attempt:
        other = json.loads((build.ROOT / f'runtime-r{args.compare_attempt}' / ('export' + suffix + '.json')).read_text())
        assert other['source_manifest'] == expected
        assert other['export_manifest'] == actual, 'main/CAS exported modes or content differ'
    record = dict(status='complete-tree-readback-passed', measured=False, argv=argv,
                  controller_sha256=build.sha(__file__), source_manifest=expected, export_manifest=actual)
    if args.capture:
        record['capture'] = args.capture
    receipt_path.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'attempt': args.attempt, 'status': record['status'], 'entries': len(actual)}), flush=True)


if __name__ == '__main__':
    main()
