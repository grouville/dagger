#!/usr/bin/env python3
"""Prepared isolated PID1 gate: one test compile, one owned no-network container.

Never uses host PID/network namespaces or existing engine resources. Requires
separate parent review/slot grant before --run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

LAB = Path(__file__).resolve().parent
IMAGE = 'sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
OWNER = 'collections-split-init-pid1-v2'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run', action='store_true')
args = parser.parse_args()
if not args.run:
    print(json.dumps({'run': False, 'compile_commands': 1, 'containers': 1, 'network': 'none', 'host_pid': False, 'bind_mounts': 'one task-owned read-only test binary', 'writable_storage': 'tmpfs /tmp only', 'engine_calls': 0, 'cloud_calls': 0}))
    raise SystemExit(0)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

recipe_path = LAB / 'manifest.json'
recipe = json.loads(recipe_path.read_text())
root = Path('/home/dagger/dag')
for rel, expected in recipe['originals'].items():
    assert (sha(root/rel) if (root/rel).is_file() else None) == expected, rel
for rel, expected in recipe['sources'].items():
    assert sha(LAB/'source'/rel) == expected, rel
out = LAB / 'privileged-gate-v1'
out.mkdir(mode=0o700, exist_ok=False)
binary = out / 'split-init-tests'
env = {k: os.environ[k] for k in ('PATH','HOME','USER','LOGNAME','TMPDIR') if k in os.environ}
env.update(GOMAXPROCS='4',GOPROXY='off',GOSUMDB='off',GOTOOLCHAIN='local',GOENV='off',GOFLAGS='',CGO_ENABLED='0',GOOS='linux',GOARCH='amd64',DO_NOT_TRACK='1')
go = '/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
cmd = [go, 'test', '-c', '-mod=readonly', '-modfile=/tmp/collections-perf/catalog-next-levers-v1/git-http/builds/engine.mod', '-overlay=' + str(LAB / 'overlay.json'), '-o', str(binary), './engine/session/initexec']
virtual_dir = root / 'engine/session/initexec'
assert not virtual_dir.exists()
virtual_dir.mkdir()
try:
    with (out / 'compile.log').open('wb') as f:
        subprocess.run(cmd, cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT, check=True, timeout=300)
finally:
    virtual_dir.rmdir()

def capture(argv, timeout=30):
    return subprocess.check_output(argv, text=True, timeout=timeout).strip()

image = json.loads(capture(['docker', 'image', 'inspect', IMAGE]))[0]
assert image['Id'] == IMAGE
assert not image['Config'].get('Volumes'), 'image would create unrequested anonymous volumes'
for assignment in image['Config'].get('Env') or []:
    key = assignment.partition('=')[0].upper()
    assert not any(token in key for token in ['CLOUD','TOKEN','SECRET','OTEL_EXPORTER','REMOTE_CACHE'])
name = 'dagger-split-init-test-' + uuid.uuid4().hex[:12]
cid = None
result = {'driver_sha256': sha(__file__), 'recipe_sha256': sha(recipe_path), 'binary_sha256': sha(binary), 'image_id': IMAGE, 'owner': OWNER, 'compile_command': cmd, 'permissions': {'privileged': True, 'network': 'none', 'host_pid': False, 'read_only_rootfs': True, 'host_bind': 'task-owned test binary, read-only', 'tmpfs': '/tmp size 64MiB'}, 'engine_calls': 0, 'cloud_calls': 0}
try:
    cid = capture(['docker', 'create', '--pull=never', '--name', name, '--label', 'dagger.perf.owner='+OWNER, '--network=none', '--privileged', '--read-only', '--user', '0:0', '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m', '--mount', 'type=bind,src='+str(binary)+',dst=/split-init-tests,readonly', '--env', 'DAGGER_TEST_INIT_PID_NAMESPACE=1', '--env', 'TMPDIR=/tmp', '--entrypoint', '/split-init-tests', IMAGE, '-test.run=^TestSplitInit(PIDNamespaceReaping|TTY)$', '-test.v', '-test.timeout=60s'])
    info = json.loads(capture(['docker','inspect',cid]))[0]
    assert info['Id'] == cid and info['Config']['Labels']['dagger.perf.owner'] == OWNER
    assert info['Image'] == IMAGE and info['HostConfig']['NetworkMode'] == 'none'
    assert not info['HostConfig']['PidMode'] and not info['HostConfig']['PortBindings']
    assert info['HostConfig']['ReadonlyRootfs'] and info['HostConfig']['Privileged']
    mounts = info['Mounts']
    binds = [m for m in mounts if m['Type'] == 'bind']
    assert len(binds) == 1 and not binds[0]['RW'] and binds[0]['Source'] == str(binary) and binds[0]['Destination'] == '/split-init-tests'
    assert all(m['Type'] == 'bind' or (m['Type'] == 'tmpfs' and m['Destination'] == '/tmp') for m in mounts)
    start = time.monotonic()
    with (out / 'test.log').open('wb') as f:
        proc = subprocess.run(['docker','start','--attach',cid], stdout=f, stderr=subprocess.STDOUT, timeout=90)
    final = json.loads(capture(['docker','inspect',cid]))[0]
    text = (out / 'test.log').read_text()
    result.update(exit_code=proc.returncode, container_exit_code=final['State']['ExitCode'], seconds=time.monotonic()-start, test_log_sha256=sha(out / 'test.log'), passed=all('--- PASS: '+n in text for n in ['TestSplitInitPIDNamespaceReaping','TestSplitInitTTY']), skipped='--- SKIP:' in text)
    assert proc.returncode == 0 and final['State']['ExitCode'] == 0 and result['passed'] and not result['skipped']
finally:
    if cid:
        final = json.loads(capture(['docker','inspect',cid]))[0]
        assert final['Id'] == cid and final['Config']['Labels']['dagger.perf.owner'] == OWNER
        capture(['docker','rm','--force',cid])
        result['owned_container_removed'] = True
    (out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result), flush=True)
