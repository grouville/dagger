#!/usr/bin/env python3
"""Build the frozen reviewed stack into a new owned dev engine; retain evidence.

Run --plan for read-only source checks, without Docker or a build. Actual use
requires normal, approved Docker access. This is not a performance benchmark.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
REPO = Path('/tmp/dagger-current-main-audit.k9g19M/repo')
SOURCE = ROOT / 'engine-source'
COMMIT = 'db9d005c715ac9d146780d783faf7f7b55d23e5e'
BOOTSTRAP = '/usr/local/bin/dagger'
BOOTSTRAP_SHA = 'e91b84361ccaadd956a39cbb39a7194b59c7e22c8acf4ebaf71cf31ed4464d8d'
RELEASE = '00cb7d3a0e8d1eb6ec672aa504db14e52a9d1e21'
PLACEHOLDER_IMAGE = 'sha256:ba0686de0d8c5543b5ff093ba7a78fa2d900f23b775fcb4983337b7e5f0319de'
NAME = 'dagger-engine.rust-fresh-' + ROOT.name.rsplit('.', 1)[1].lower()
OWNER = ROOT.name
IMAGE = 'localhost/' + NAME


def environment():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('GIT_', 'DAGGER_', '_EXPERIMENTAL_DAGGER_', 'OTEL_'))}
    env.pop('DOCKER_CONTEXT', None)
    env.update(DOCKER_HOST='unix:///var/run/docker.sock', DO_NOT_TRACK='1',
               DNT='1', DAGGER_LEAVE_OLD_ENGINE='1')
    # Keep the existing download cache, but isolate CLI configuration and state.
    for kind in ('CONFIG', 'DATA', 'STATE'):
        env[f'XDG_{kind}_HOME'] = str(ROOT / 'build-xdg' / kind.lower())
    return env


def fingerprint(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(*argv, cwd=REPO):
    return subprocess.check_output(argv, cwd=cwd, env=environment(), text=True).strip()


def deploy_command():
    return [BOOTSTRAP, '--x-release', RELEASE, 'api', 'call', 'dev',
            '--docker=unix:///var/run/docker.sock', 'deploy', '--name=' + NAME,
            '--image=' + IMAGE, '--platform=linux/amd64', '--debug-endpoint=false',
            '--output', str(ROOT / 'bin')]


def inspect():
    item = json.loads(read('docker', 'inspect', NAME))[0]
    # Deliberately retain only identity/state, never a container's environment.
    return {key: item[key] for key in ('Id', 'Image', 'State', 'RestartCount')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    if read('git', 'rev-parse', 'HEAD') != COMMIT:
        raise RuntimeError('Reviewed HEAD changed; refresh this frozen build plan first')
    if read('git', 'diff', 'HEAD'):
        raise RuntimeError('Reviewed tracked source is dirty; do not omit changes silently')
    if fingerprint(BOOTSTRAP) != BOOTSTRAP_SHA:
        raise RuntimeError('Bootstrap CLI changed; review and update its identity first')
    record = dict(status='planned', source=str(SOURCE), commit=COMMIT,
                  reviewed_repo=str(REPO), upstream_base='6bf59d50654ce9244ebeee1cc090b7dce3fe3083',
                  newer_upstream_observed='6bf59d50654ce9244ebeee1cc090b7dce3fe3083',
                  argv=deploy_command(), bootstrap_sha256=BOOTSTRAP_SHA,
                  engine_name=NAME, image_alias=IMAGE, state_volume=NAME,
                  performance_benchmark=False, current_upstream_claim=False,
                  upstream_observed_at='2026-09-12T05:04:00Z',
                  candidate_status='unsigned scratch rebase; not published',
                  original_dirty_workspace_modified=False,
                  side_effects=['add detached source worktree',
                                'create and replace only a new never-started placeholder',
                                'build/load engine image and export matching CLI',
                                'start privileged dev engine with new named state volume',
                                'run one ordinary no-module GraphQL smoke query'],
                  commands=[])
    if args.plan:
        print(json.dumps(record, indent=2))
        return 0
    if os.uname().sysname != 'Linux' or os.uname().machine not in ('x86_64', 'amd64'):
        raise RuntimeError('This frozen runner targets the recorded Linux/amd64 host')
    if SOURCE.exists() or (ROOT / 'bin').exists() or (ROOT / 'run.json').exists():
        raise RuntimeError('Run directory already used; preserve it and make a new reviewed runner')

    # Check the daemon and exact targets before mutating anything.
    record['docker_server_version'] = read('docker', 'version', '--format', '{{.Server.Version}}')
    if not record['docker_server_version']:
        raise RuntimeError('Docker returned no server version')
    if read('docker', 'ps', '-aq', '--filter', 'name=^/' + NAME + '$'):
        raise RuntimeError('Engine name already exists; refusing to replace it')
    if NAME in read('docker', 'volume', 'ls', '--format', '{{.Name}}').splitlines():
        raise RuntimeError('State volume already exists; this must be a fresh engine')
    if read('docker', 'image', 'inspect', PLACEHOLDER_IMAGE, '--format', '{{.Id}}') != PLACEHOLDER_IMAGE:
        raise RuntimeError('Expected local placeholder image is unavailable')
    if read('docker', 'image', 'ls', '--format', '{{.Repository}}:{{.Tag}}', IMAGE):
        raise RuntimeError('Output image alias already exists; refusing to overwrite it')

    with (ROOT / 'run.json').open('x') as stream:
        json.dump(record, stream, indent=2)

    def save():
        (ROOT / 'run.json').write_text(json.dumps(record, indent=2) + '\n')

    def run(label, argv, cwd=SOURCE, stdin=None, timeout=None):
        begin = time.perf_counter_ns()
        entry = dict(label=label, argv=argv, cwd=str(cwd), start_unix_ns=time.time_ns())
        record['commands'].append(entry)
        save()
        with (ROOT / (label + '.log')).open('x') as output:
            result = subprocess.run(argv, cwd=cwd, env=environment(), input=stdin,
                                    text=True, stdout=output, stderr=subprocess.STDOUT,
                                    timeout=timeout)
        entry.update(exit_code=result.returncode, elapsed_ms=(time.perf_counter_ns()-begin)/1e6,
                     end_unix_ns=time.time_ns())
        save()
        if result.returncode:
            raise RuntimeError(f'{label} exited {result.returncode}; see {ROOT / (label + ".log")}')

    print(f'Build log: {ROOT / "engine-build.log"}', flush=True)
    try:
        record['status'] = 'creating-source'
        run('source-worktree', ['git', 'worktree', 'add', '--detach', str(SOURCE), COMMIT], cwd=REPO)
        if read('git', 'rev-parse', 'HEAD', cwd=SOURCE) != COMMIT or read('git', 'status', '--porcelain', cwd=SOURCE):
            raise RuntimeError('Detached source did not match the clean frozen commit')
        # Current dev deploy unconditionally removes its named target before
        # starting it. Supply a new owned, never-started placeholder, not an old
        # user engine. No running process or useful data is removed this way.
        run('placeholder-create', ['docker', 'create', '--name', NAME,
                                 '--label', 'dagger.rust.bench-owner=' + OWNER, PLACEHOLDER_IMAGE])
        placeholder = inspect()
        label = read('docker', 'inspect', '--format', '{{index .Config.Labels "dagger.rust.bench-owner"}}', NAME)
        if placeholder['State']['Status'] != 'created' or label != OWNER:
            raise RuntimeError('Placeholder ownership/state mismatch')
        record['placeholder'] = placeholder
        record['status'] = 'building'
        save()
        run('engine-build', deploy_command())
        record['engine_after_build'] = inspect()
        if not record['engine_after_build']['State']['Running']:
            raise RuntimeError('New engine is not running')
        actual_image = read('docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}')
        if record['engine_after_build']['Image'] != actual_image:
            raise RuntimeError('Running engine image does not match the built alias')
        record['cli_sha256'] = fingerprint(ROOT / 'bin/dagger')
        record['source_diff_after_build'] = read('git', 'diff', '--stat', 'HEAD', cwd=SOURCE)
        record['status'] = 'smoke-testing'
        save()
        run('engine-query', [str(ROOT / 'bin/dagger'), 'api', 'query', '--no-load-module'],
            cwd=ROOT, stdin='{ __typename }\n', timeout=120)
        record['engine_after_smoke'] = inspect()
        if record['engine_after_smoke']['Id'] != record['engine_after_build']['Id']:
            raise RuntimeError('Smoke query unexpectedly replaced the new engine')
        record['status'] = 'built-and-query-passed'
        record['placeholder_removed'] = True
        save()
        print(json.dumps({key: record[key] for key in
                         ('status', 'commit', 'engine_name', 'state_volume', 'cli_sha256')}, indent=2), flush=True)
        print(f'CLI: {ROOT / "bin/dagger"}\nEvidence: {ROOT / "run.json"}', flush=True)
        return 0
    except BaseException as error:
        record['status'] = 'failed'
        record['error'] = str(error)
        save()
        print(f'Build failed; all created state and logs retained at {ROOT}', flush=True)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
