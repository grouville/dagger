#!/usr/bin/env python3
"""Prepare constructor-policy comparison. Copying/generation require explicit flags."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

LAB = Path(__file__).resolve().parent
SOURCE = LAB.parent / 'backend-go-cache/measured/cache/greetings-api'
OUT = LAB / 'measurement'
BACKEND = '.dagger/modules/backend'
METHODS = ('Binary', 'Build', 'Container', 'GoTestBase', 'Serve')
CLI = '/tmp/collections-perf/rebase-main/dagger'
ENGINE = 'dagger-engine.collections-disk-abba-2'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_metadata(app):
    source = (app / BACKEND / 'main.go').read_text()
    generated = (app / BACKEND / 'dagger.gen.go').read_text()
    matches = list(re.finditer(r'dag.Function\("([^"]+)"', generated))
    blocks = {m.group(1): generated[m.start():matches[i + 1].start() if i + 1 < len(matches) else len(generated)]
              for i, m in enumerate(matches)}
    assert set(blocks) == set(METHODS) | {'New'}, sorted(blocks)
    for name in METHODS:
        block = blocks[name]
        assert block.count('WithCachePolicy(dagger.FunctionCachePolicyPerSession)') == 1, (name, block)
        expected_line = next(i for i, line in enumerate(source.splitlines(), 1)
                             if line.startswith('func (b *Backend) ' + name + '('))
        assert f'WithSourceMap(dag.SourceMap("main.go", {expected_line}, 1))' in block, (name, expected_line)
    assert generated.count('WithCachePolicy(') == 5
    assert 'WithCachePolicy(' not in blocks['New']
    assert 'DefaultPath: "/"' in blocks['New']
    assert 'Ignore: []string{".git", "**/node_modules", "website"}' in blocks['New']
    assert 'WithUp()' in blocks['Serve']
    return {'sha256': digest(generated.encode()), 'session_methods': list(METHODS),
            'constructor': 'DEFAULT', 'default_path_ignore_up_and_source_maps': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--copy', action='store_true')
    p.add_argument('--validate', action='store_true')
    args = p.parse_args()
    commands = {v: [CLI, '--engine', 'container://' + ENGINE, '-y', 'generate', 'dagger-go-sdk/generate']
                for v in ('control', 'constructor')}
    if not args.copy and not args.validate:
        print(json.dumps({'status': 'prepared only; no copies or executions',
                          'source': str(SOURCE), 'destination': str(OUT),
                          'normal_generation_commands': commands}, indent=2))
        return
    if args.copy:
        OUT.mkdir(exist_ok=False)
        source = (LAB / 'main.go').read_bytes()
        baseline = (LAB.parent / 'backend-go-cache/main.after.go').read_bytes()
        assert (SOURCE / BACKEND / 'main.go').read_bytes() == baseline
        paths = ['main.go', 'main_test.go', 'e2e_test.go', 'dagger.toml', 'dagger.lock',
                 BACKEND + '/main.go', BACKEND + '/dagger.gen.go', BACKEND + '/dagger-module.toml']
        manifest = {'source': str(SOURCE), 'cli': CLI, 'cli_sha256': digest(Path(CLI).read_bytes()),
                    'engine': ENGINE, 'source_sha256': {x: digest((SOURCE / x).read_bytes()) for x in paths},
                    'generation_status': 'NOT GENERATED: do not benchmark until --validate succeeds',
                    'normal_generation_commands': commands,
                    'control': 'module opt-out true; five explicit session methods',
                    'constructor': 'module opt-out false; same five explicit session methods'}
        for v in commands:
            app = OUT / v / 'greetings-api'
            shutil.copytree(SOURCE, app, symlinks=True)
            (app / BACKEND / 'main.go').write_bytes(source)
            config = (app / BACKEND / 'dagger-module.toml').read_text()
            assert config.count('disableDefaultFunctionCaching = true') == 1
            if v == 'constructor':
                config = config.replace('disableDefaultFunctionCaching = true', 'disableDefaultFunctionCaching = false')
            (app / BACKEND / 'dagger-module.toml').write_text(config)
        (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if args.validate:
        results = {v: validate_metadata(OUT / v / 'greetings-api') for v in commands}
        assert results['control']['sha256'] == results['constructor']['sha256'], results
        for filename in ('main.go', 'dagger.gen.go'):
            assert (OUT / 'control/greetings-api' / BACKEND / filename).read_bytes() == (OUT / 'constructor/greetings-api' / BACKEND / filename).read_bytes()
        (OUT / 'metadata-validation.json').write_text(json.dumps(results, indent=2) + '\n')
        manifest = json.loads((OUT / 'manifest.json').read_text())
        manifest['generation_status'] = 'normal Go SDK generation completed; emitted metadata validated'
        manifest['metadata_validation'] = results
        (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
