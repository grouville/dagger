#!/usr/bin/env python3
"""Owned CAS foundation tests through the supported engine-dev workflow."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'engine'
HEAD = '523f3fe37b0d03f8fd7ee1aaa77b2ca0f1978b59'
BOOT = '/usr/local/bin/dagger'
RELEASE = '00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith(
        ('GIT_', 'DAGGER_', '_DAGGER_', '_EXPERIMENTAL_DAGGER_', 'OTEL_', 'DOCKER_', 'XDG_'))
        and k.upper() not in ('TRACEPARENT', 'TRACESTATE', 'BAGGAGE', 'SSH_AUTH_SOCK')}
    env.update(DOCKER_HOST='unix:///var/run/docker.sock', DO_NOT_TRACK='1', DNT='1',
               DAGGER_LEAVE_OLD_ENGINE='1', GIT_OPTIONAL_LOCKS='0')
    for category in ('CONFIG', 'CACHE', 'DATA', 'STATE'):
        env['XDG_' + category + '_HOME'] = str(ROOT/'build-xdg'/category.lower())
    return env

def read(argv, env):
    return subprocess.check_output(argv, env=env, text=True, stderr=subprocess.PIPE, timeout=60).strip()

def inventory_compatible(record):
    """Accept stable builds or the one explicitly reviewed external addition."""
    if record["inventory_unchanged"]:
        return True
    # Build-r8 exported successfully with identical source pins. Its only
    # inventory delta was an unrelated dagger-engine.pp1 appearing. This
    # accepts that exact artifact receipt, not arbitrary inventory changes,
    # and says nothing about whether a benchmark host is idle.
    reviewed = ROOT / 'build-r8/receipt.json'
    return (reviewed.exists()
            and sha(reviewed) == 'aa4f5f25d0b7bb7b7e972451e643a9fd27d559425c809b6d0787dbd94fcd7d81'
            and record == json.loads(reviewed.read_text()))

def pins(env, source=SOURCE):
    def git(*args): return read(['git', '-C', str(source), *args], env)
    assert (source/'.git').is_dir() and not (source/'.git/objects/info/alternates').exists()
    git('merge-base', '--is-ancestor', HEAD, 'HEAD')
    names = set(git('diff', '--name-only', 'HEAD').splitlines())
    names.update(git('ls-files', '--others', '--exclude-standard').splitlines())
    # Local dependency archive is a build input too, including files hidden by
    # its own .gitignore. Hash symlink targets, never follow them outside it.
    dependency = source/'internal/containerd-batch'
    if dependency.exists():
        names.update(str(path.relative_to(source)) for path in dependency.rglob('*')
                     if path.is_symlink() or path.is_file())
    def fingerprint(path):
        return {'symlink': os.readlink(path)} if path.is_symlink() else sha(path)
    return {'head': git('rev-parse', 'HEAD'), 'files': {name: fingerprint(source/name) for name in sorted(names)}}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt')
    parser.add_argument('stage', choices=('unit', 'privileged', 'build'))
    parser.add_argument('--run', default='^Test')
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--diagnostic-main', action='store_true', help='build main plus recorded diagnostic instrumentation, never label clean main')
    parser.add_argument('--xattrs-only', action='store_true', help='use the owned xattr-only comparison source')
    parser.add_argument('--pkg', choices=('./util/layercopy', './internal/fsutil', './engine/contenthash', './engine/snapshots', './engine/snapshots/containerd', './engine/filesync', './core', './core/integration', './dagql', './dagql/persistdb'), default='./engine/filesync')
    args = parser.parse_args()
    assert args.attempt.startswith('build-r') and args.attempt[7:].isdigit()
    env = environment()
    assert sum((args.baseline, args.diagnostic_main, args.xattrs_only)) <= 1
    source = ROOT/'engine-xattrs' if args.xattrs_only else (ROOT/'engine-main' if args.baseline or args.diagnostic_main else SOURCE)
    before_pins = pins(env, source)
    if args.baseline:
        assert before_pins == {'head': HEAD, 'files': {}}, 'main baseline must be clean and pinned'
    assert sha(BOOT) == 'e91b84361ccaadd956a39cbb39a7194b59c7e22c8acf4ebaf71cf31ed4464d8d'
    def inventory():
        return sorted(read(['docker', 'ps', '-a', '--no-trunc', '--format',
                            '{{.ID}} {{.Names}} {{.State}}'], env).splitlines())
    before = inventory()
    assert any(row.endswith(' dagger-engine-'+RELEASE+' running') for row in before)
    out = ROOT/args.attempt
    out.mkdir(exist_ok=False)
    common = [BOOT, '--x-release', RELEASE, 'api', 'call', 'engine-dev']
    argv = common + (['test', '--pkg='+args.pkg,
        '--run='+args.run,
        '--parallel=1', '--count='+str(args.count), '--race', '--timeout=300s', '--test-verbose=true']
        if args.stage == 'unit' else ['container', '--platform=linux/amd64',
        'as-tarball', '--forced-compression=Gzip', '--output', str(out/'engine.tar')])
    if args.stage == 'privileged':
        test_args = ['go', 'test', '-tags=privileged', '-v', '-race', '-parallel=1',
                     '-count='+str(args.count), '-timeout=300s', '-run='+args.run, args.pkg]
        assert all(',' not in arg for arg in test_args)
        argv = [BOOT, '--x-release', RELEASE, '-m', '.dagger/modules/go',
                'api', 'call', '--source=.', '--cgo', 'env',
                'with-mounted-temp', '--path=/tmp',
                'with-exec', '--insecure-root-capabilities', '--args='+','.join(test_args), 'stdout']
    record = {'status': 'running', 'stage': args.stage, 'argv': argv,
              'source_role': 'xattrs-only-with-diagnostics' if args.xattrs_only else ('main-with-diagnostics' if args.diagnostic_main else ('clean-main' if args.baseline else 'candidate')),
              'source_pins': before_pins, 'source_directory': str(source), 'controller_sha256': sha(__file__),
              'inventory_before': before, 'started_ns': time.time_ns(),
              'performance_claim': False}
    def save(): (out/'receipt.json').write_text(json.dumps(record, indent=2)+'\n')
    save()
    try:
        with (out/'build.log').open('x') as stream:
            result = subprocess.run(argv, cwd=source, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=1800)
        record['exit_code'] = result.returncode
        assert result.returncode == 0, 'engine-dev failed; retain build.log'
        assert pins(env, source) == before_pins, 'source moved during build'
        if args.stage == 'build':
            record['archive_sha256'] = sha(out/'engine.tar')
        record['status'] = 'exported' if args.stage == 'build' else 'tests-passed'
    except BaseException as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        record['ended_ns'] = time.time_ns()
        record['inventory_after'] = inventory()
        record['inventory_unchanged'] = record['inventory_after'] == before
        save()
    print(json.dumps({key: record[key] for key in ('status', 'stage', 'exit_code', 'inventory_unchanged')}), flush=True)

if __name__ == '__main__':
    main()
