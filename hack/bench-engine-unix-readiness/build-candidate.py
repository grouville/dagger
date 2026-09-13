#!/usr/bin/env python3
"""Build only Unix socket readiness on top of the exact measured stream engine.

The same current inventory CLI will drive both engine treatments. No benchmark
timing, image publication, existing-engine replacement, or cache pruning here.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'engine-source'
UNIT = HERE / 'source'
PREVIOUS = Path('/tmp/dagger-stream-close-order.6U5EYNjb/engine-builds/builds.json')
HELPER = Path('/tmp/dagger-rust-current-main-engine.QepteZyL/build.py')
CLI = Path('/tmp/dagger-container-inventory.NMh2Z3QV/dagger-candidate')
PARENT = '503d3410ef3df63fa6bc7a55c5c2453c4951c2c2'
MAIN = '7c35e6274737acff0f6bd76614abb5e04efa7d12'
NAME = 'dagger-unix-readiness-ufjy9dsi'
CHANGES = {'cmd/dialstdio/main.go', 'cmd/dialstdio/main_test.go', 'cmd/dialstdio/stdio_test.go'}
spec = importlib.util.spec_from_file_location('base', HELPER)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.ROOT = HERE / 'engine-builds/B'
base.REPO = SOURCE
base.SOURCE = SOURCE
base.NAME = NAME
base.IMAGE = 'localhost/' + NAME


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(*argv, cwd=SOURCE):
    return subprocess.check_output(argv, cwd=cwd, env=base.environment(), text=True).strip()


def hashes(source):
    assert read('git', 'rev-parse', 'HEAD', cwd=source) == PARENT
    assert read('git', 'merge-base', MAIN, 'HEAD', cwd=source) == MAIN
    assert not read('git', 'diff', '--check', cwd=source)
    paths = set(read('git', 'diff', 'HEAD', '--name-only', cwd=source).splitlines())
    paths.update(read('git', 'ls-files', '--others', '--exclude-standard', cwd=source).splitlines())
    return {path: sha(source/path) for path in sorted(paths)}


def inspect(name):
    item = json.loads(read('docker', 'inspect', name))[0]
    return {key: item[key] for key in ('Id', 'Image', 'State', 'RestartCount')}


def main():
    assert sys.argv[1:] in (['--plan'], ['--execute'])
    assert sha(HELPER) == '6a56a60dfcefc3a5fe4460382b05dcf754cd7f8f632a862d1dd0018388b7ef4c'
    assert sha(CLI) == '6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad'
    assert sha(base.BOOTSTRAP) == base.BOOTSTRAP_SHA
    previous = json.loads(PREVIOUS.read_text())
    assert previous['status'] == 'built-and-query-passed'
    assert previous['parent'] == PARENT and previous['upstream_main'] == MAIN
    a = dict(next(item for item in previous['builds'] if item['side'] == 'B'))
    a['side'] = 'A'
    assert a['status'] == 'built-and-query-passed'
    assert all(command['exit_code'] == 0 for command in a['commands'])
    old = previous['source_hashes']['B']
    assert hashes(Path(a['source'])) == old
    assert sha(Path(a['source'])/'cmd/dialstdio/main.go') == 'b83c1aff04f5f0b95e6788dcf69d4c3dbbb08b49aa3efb662e78fdcfd56183c1'
    frozen = hashes(SOURCE)
    assert set(frozen) == set(old) | CHANGES
    assert all(frozen[path] == expected for path, expected in old.items())
    assert all(frozen[path] == sha(UNIT/path) for path in CHANGES)
    root = HERE/'engine-builds'
    plan = dict(status='planned', parent=PARENT, upstream_main=MAIN, scope=__doc__,
                previous_build=str(PREVIOUS), previous_build_sha256=sha(PREVIOUS),
                source_roots={'A': a['source'], 'B': str(SOURCE)},
                source_hashes={'A': old, 'B': frozen}, differences=sorted(CHANGES),
                controller_sha256=sha(__file__), cli=str(CLI), cli_sha256=sha(CLI),
                builds=[a])
    if sys.argv[1:] == ['--plan']:
        print(json.dumps({key: value for key, value in plan.items() if key not in ('source_hashes', 'builds')}, indent=2))
        return
    assert not root.exists(), 'preserve any previous attempt; use a new owner'
    assert read('docker', 'image', 'inspect', a['engine_after_smoke']['Image'], '--format', '{{.Id}}') == a['engine_after_smoke']['Image']
    assert not read('docker', 'ps', '-aq', '--filter', 'name=^/'+NAME+'$')
    assert NAME not in read('docker', 'volume', 'ls', '--format', '{{.Name}}').splitlines()
    assert not read('docker', 'image', 'ls', '--format', '{{.Repository}}:{{.Tag}}', base.IMAGE)
    assert read('docker', 'image', 'inspect', base.PLACEHOLDER_IMAGE, '--format', '{{.Id}}') == base.PLACEHOLDER_IMAGE
    retained = inspect(a['engine_name'])
    assert retained['Id'] == a['engine_after_smoke']['Id'] and retained['Image'] == a['engine_after_smoke']['Image']
    (root/'B').mkdir(parents=True)
    item = dict(side='B', source=str(SOURCE), engine_name=NAME, commands=[], status='testing')
    plan['builds'].append(item)
    plan['status'] = 'running'

    def save():
        (root/'builds.json').write_text(json.dumps(plan, indent=2)+'\n')

    def run(label, argv, stdin=None, extra_env=None):
        assert hashes(SOURCE) == frozen
        step = dict(label=label, argv=argv, start_ns=time.time_ns())
        item['commands'].append(step)
        save()
        print(label, flush=True)
        with (root/'B'/(label+'.log')).open('xb') as output:
            result = subprocess.run(argv, cwd=SOURCE, env=base.environment() | (extra_env or {}),
                                    input=stdin, text=True, stdout=output, stderr=subprocess.STDOUT)
        step.update(exit_code=result.returncode, end_ns=time.time_ns())
        save()
        assert result.returncode == 0, label+' failed; preserve source and logs'

    save()
    try:
        run('dialstdio-race', [str(CLI), 'api', 'call', 'engine-dev', 'test', '--pkg=./cmd/dialstdio',
                              '--run=^TestDial', '--parallel=1', '--timeout=90s', '--count=3',
                              '--race=true', '--test-verbose=true'],
            extra_env={'DAGGER_ENGINE': 'container://'+a['engine_name']})
        run('placeholder-create', ['docker', 'create', '--name', NAME, '--label',
                                  'dagger.rust.bench-owner='+HERE.name, base.PLACEHOLDER_IMAGE])
        item['placeholder'] = inspect(NAME)
        assert item['placeholder']['State']['Status'] == 'created'
        assert read('docker', 'inspect', '--format', '{{index .Config.Labels "dagger.rust.bench-owner"}}', NAME) == HERE.name
        item['status'] = 'building'
        save()
        run('engine-build', base.deploy_command())
        item['engine_after_build'] = inspect(NAME)
        assert item['engine_after_build']['State']['Running']
        assert read('docker', 'image', 'inspect', base.IMAGE, '--format', '{{.Id}}') == item['engine_after_build']['Image']
        run('smoke', [str(CLI), 'api', 'query', '--no-load-module'], stdin='{ __typename }\n',
            extra_env={'DAGGER_ENGINE': 'container://'+NAME})
        item['engine_after_smoke'] = inspect(NAME)
        assert item['engine_after_smoke']['Id'] == item['engine_after_build']['Id']
        assert item['engine_after_smoke']['Image'] != a['engine_after_smoke']['Image']
        assert hashes(SOURCE) == frozen and hashes(Path(a['source'])) == old
        now = inspect(a['engine_name'])
        assert all(now[key] == retained[key] for key in ('Id', 'Image', 'RestartCount'))
        item['status'] = plan['status'] = 'built-and-query-passed'
    except BaseException as error:
        plan.update(status='failed', error=repr(error))
        raise
    finally:
        plan['ended_ns'] = time.time_ns()
        save()


if __name__ == '__main__':
    main()
