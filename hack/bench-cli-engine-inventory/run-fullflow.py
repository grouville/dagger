#!/usr/bin/env python3
"""Three matched current-main inventory-prefilter CLI pairs on one verified-stream engine.

All images are locally preinstalled; each measured engine/Cargo state is empty.
No total-install or unprofiled claim. Existing correctness gates remain intact.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent
CLI_OWNER = Path("/tmp/dagger-container-inventory.NMh2Z3QV")
CONTROL_OWNER = Path("/tmp/dagger-cli-readiness-current.AS6z1ng4")
ADAPTER_OWNER = Path("/tmp/dagger-cli-readiness-auto.C70FUvMf")
ENGINE_REF = "localhost/dagger-stream-close-order-6u5eynjb:latest"
BASE = Path('/tmp/dagger-rust-current-main-engine.QepteZyL')
BENCH = BASE / 'engine-source/hack/bench-rust-loop'
CLIS = {'A': CONTROL_OWNER / 'dagger-candidate',
        'B': CLI_OWNER / 'dagger-candidate'}
ADAPTER = ADAPTER_OWNER / 'run-cli-provision-check.py'
RECEIVER = Path('/tmp/dagger-rust-perf-sprint.1qnbuQ9j/otlpdump')
RAW = HERE / 'flow-telemetry.jsonl'
ENDPOINT = 'http://127.0.0.1:43241'
RUST = 'rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b'
RIPGREP = Path('/tmp/dagger-rust-ripgrep-reference')
HASHES = {
    CLIS['A']: 'd4eb2c81edc8c04a9512d276dce1346f73e45dbc608e9812662623b90e694f86',
    CLIS['B']: '6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad',
    CLI_OWNER / 'build-inputs.sha256': 'e617c45618290bbe31555c4f6e5e0ceae86b3756451d9b51d03d55f99e1c80f8',
    CONTROL_OWNER / 'build-inputs.sha256': '28a1d8f7293394b73ab13776dbbb14bb5bfbe4f0a9f9585f3f9606c1d8c9f6a3',
    CLI_OWNER / 'after-contract-unit.log': '87d72c8e48675f8d9cdd2158ff1310801b17b4f55f4f0437d9c61c507b2db32f',
    CLI_OWNER / 'docker-contract.log': '16e7561df603de231f3eed186c4bb115aeb258475646dc1dda31e99e1106c721',
    CLI_OWNER / 'test-docker-contract.sh': '924879ca0bc49351aac67698c145a92a4ed1039c88f58e9ac5522971a1e51795',
    CLI_OWNER / 'build.sh': 'feac745dbc568d6d99d9bada5be11319380a14f1684e79eb531af12bfc609b5c',
    BENCH / 'fixtures/ripgrep-bstr-1.12.0.patch': '855d4dfc3bdc090564ac451c41d8d98e44af110f43b78d4ba8b3d00215d642d8',
    BENCH / 'profile-command.py': '9111c7d9fe6d13266e899bc1048bf7aee66208024c6980c7bd607bfe78123201',
    ADAPTER: 'e68d915da2e6c3df3bbf8acd02fb1ca9f24e5de1b2b64b1f103597acfb9b5144',
    ADAPTER_OWNER / 'debug-get': 'd50874b7f7c0235bececcb4dbad34655dcadf06452cc3f767d11a9b6160cc5d8',
    ADAPTER_OWNER / 'debug-get.go': 'dd4752ab73cd53327655b8a86e430c8615e4745be5af7bc35f6ca63b58114be5',
    RECEIVER: 'f2aef556572da41578a0336248b4c6d1972b9d050df2622e57303555752f9b38',
    BENCH / 'module/main.dang': 'f6e119c3b7be439df46a6ea9b74c368126751e0a141b2e5ebb699a4b0f0681f1',
    BENCH / 'module/dagger-module.toml': '80ceb12a068bb2c86041ba35bdcb24edada8ae228b77450de2ce917caa2ec8e5',
    BENCH / 'fixtures/rust-toolchain-rustfmt.toml': '173153c62c4ba6dc43f73eba9149e76deef633614b7b5a81568ee97aac12f32e',
    Path('/tmp/dagger-rust-wcprof-otel'): 'de3bde25361254d784a211a9fdfec5043459a7a211b9e2a012252ebfbd45a8ba',
}

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    assert sys.argv[1:] == ['--execute'], 'explicit --execute required'
    cli_source = Path('/tmp/dagger-cli-readiness-publish.EF1gh3BO/repo')
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cli_source, text=True).strip() == '06a8b73a19b67da188da3f833ed78b650881c20f'
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=cli_source, text=True).strip()
    subprocess.run(['sha256sum', '--check', str(CONTROL_OWNER / 'build-inputs.sha256')], cwd=cli_source, check=True)
    candidate_source = CLI_OWNER / 'source'
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=candidate_source,text=True).strip() == '06a8b73a19b67da188da3f833ed78b650881c20f'
    expected_changes = {' M engine/client/drivers/apple.go', ' M engine/client/drivers/container.go', ' M engine/client/drivers/container_create_test.go', ' M engine/client/drivers/container_test.go', ' M engine/client/drivers/docker.go', '?? engine/client/drivers/container_inventory_test.go', '?? engine/client/drivers/container_inventory_docker_test.go'}
    assert set(subprocess.check_output(['git','status','--porcelain'],cwd=candidate_source,text=True).splitlines()) == expected_changes
    subprocess.run(['sha256sum','--check',str(CLI_OWNER/'build-inputs.sha256')],cwd=candidate_source,check=True)
    assert not RAW.exists(), 'never append to a prior capture'
    for path, expected in HASHES.items():
        assert sha(path) == expected, str(path)
    # Freeze the controller/analysis before capture, not after seeing outcomes.
    for name in ('run-fullflow.py','analyze-fullflow.py','summarize-fullflow.py','phase-summary.py','audit-ordinary.py','driver-summary.py'):
        HASHES[HERE/name] = sha(HERE/name)
    env = {key: val for key, val in os.environ.items() if not key.startswith(
        ('GIT_', 'DAGGER_', '_DAGGER_', '_EXPERIMENTAL_DAGGER_', 'OTEL_'))}
    env.pop('DOCKER_CONTEXT', None)
    env.pop('GODEBUG', None)
    env.update(DO_NOT_TRACK='1', DNT='1', GIT_OPTIONAL_LOCKS='0',
               DOCKER_HOST='unix:///var/run/docker.sock',
               OTEL_EXPORTER_OTLP_ENDPOINT=ENDPOINT,
               OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=ENDPOINT + '/v1/logs',
               OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=ENDPOINT + '/v1/metrics',
               OTEL_EXPORTER_OTLP_TRACES_LIVE='1')
    def read(*argv, cwd=BASE / 'engine-source'):
        return subprocess.check_output(argv, cwd=cwd, env=env, text=True).strip()
    def inventory():
        return sorted(read('docker', 'ps', '-a', '--no-trunc', '--format', '{{.ID}} {{.Names}}').splitlines())
    def inventory_summary(rows):
        return dict(count=len(rows), sha256=hashlib.sha256(('\n'.join(rows)+'\n').encode()).hexdigest())
    initial_inventory = inventory()
    # Local-only evidence: unrelated names are not part of public benchmark data.
    (HERE/'host-inventory.local.json').write_text(json.dumps(initial_inventory, indent=2)+'\n')
    assert read('git', 'rev-parse', 'HEAD') == 'db9d005c715ac9d146780d783faf7f7b55d23e5e'
    assert not read('git', 'status', '--porcelain')
    assert read('git', 'rev-parse', 'HEAD', cwd=RIPGREP) == '3fce3b5bb0236da2df6d99672afb8a719642eca7'
    assert not read('git', 'status', '--porcelain', cwd=RIPGREP)
    native_image = read('docker', 'image', 'inspect', RUST, '--format', '{{.Id}}')
    build_path = Path('/tmp/dagger-stream-close-order.6U5EYNjb/engine-builds/builds.json')
    build = json.loads(build_path.read_text())
    assert build['status'] == 'built-and-query-passed'
    assert build['parent'] == '503d3410ef3df63fa6bc7a55c5c2453c4951c2c2'
    assert build['upstream_main'] == '7c35e6274737acff0f6bd76614abb5e04efa7d12'
    assert 'engine/server/resolver/streamed_fetch.go' in build['differences']
    assert 'internal/bench-image-stream/containerd/core/diff/apply/apply.go' in build['differences']
    assert all('bench-parser-stats' not in p for p in build['differences'])
    images = {}
    for entry in build['builds']:
        side = entry['side']
        assert entry['status'] == 'built-and-query-passed'
        assert read('git','rev-parse','HEAD',cwd=Path(entry['source'])) == build['parent']
        for relative, expected in build['source_hashes'][side].items():
            assert sha(Path(entry['source']) / relative) == expected, relative
        images[side] = entry['engine_after_smoke']['Image']
        assert read('docker','image','inspect',images[side],'--format','{{.Id}}') == images[side]
    assert set(images) == {'A','B'} and images['A'] != images['B']
    # Only the CLI differs. Both fresh treatments use the last validated
    # stream candidate, not two different engines or result-cache histories.
    images = {'A': images['B'], 'B': images['B']}
    assert images['A'] == images['B'] and CLIS['A'] != CLIS['B']
    assert read('docker','image','inspect',ENGINE_REF,'--format','{{.Id}}') == images['B']
    for owner, source in ((CLI_OWNER, candidate_source), (CONTROL_OWNER, cli_source)):
        for line in (owner/'build-inputs.sha256').read_text().splitlines():
            expected, relative = line.split(maxsplit=1)
            HASHES[source/relative] = expected
    cohort = Path(tempfile.mkdtemp(prefix='dagger-rust-cli-autoprovision-ab-'))
    meta = dict(status='running', order='ABBAAB', comparison=True,
                scope='Three matched control-vs-inventory-prefilter CLI pairs AB/BA/AB on the identical validated stream engine and official gzip Rust image, default registry configuration. CLI itself provisions each new engine using image+docker with cleanup disabled solely to preserve existing unrelated engines. Preinstalled engine image; full first CLI includes provisioning. Post-timer profile/cache retrieval uses a local helper copied only after the first CLI exits. Fresh independent Cargo/engine states; three repeated source edits and one actual bstr upgrade each. First-check/dependency timings profiled; other warm timings omit --profile but export local OTLP. Not full installation.',
                cli_paths={side: str(path) for side, path in CLIS.items()},
                cli_sha256={side: HASHES[path] for side, path in CLIS.items()},
                cli_source=str(cli_source), cli_source_commit='06a8b73a19b67da188da3f833ed78b650881c20f',
                candidate_cli_source=str(candidate_source), candidate_cli_base='06a8b73a19b67da188da3f833ed78b650881c20f',
                cli_upstream_main='7c35e6274737acff0f6bd76614abb5e04efa7d12',
                note='Both CLIs based on main7c35 reverified before capture. Both include the same validated readiness behavior. B adds Docker server-side name prefiltering before container summary generation, retaining Go-side selection and cleanup checks. Other backend commands and all session/cache ownership remain unchanged. Current host inventory has many retained containers; this is not a universal fixed saving. Same validated stream engine image on both sides. Default registry route, no custom config or prewarming. Docker/CLI/engine images/module/native image preinstalled; host page/CDN caches not purged.',
                independent_pairs=3, repeated_samples_per_flow=3,
                engine_provisioning='ordinary-image-driver-inside-cli',
                engine_reference=ENGINE_REF, diagnostic_helper='post-first-CLI copy, loopback-only debug retrieval',
                dependency_upgrade='bstr 1.12.0 -> 1.13.0 once per fresh run',
                preinstalled=['Docker', 'CLI', 'engine image', 'local module', 'native Rust image'],
                image_ids=images, native_image_id=native_image,
                candidate_build=str(build_path), candidate_build_sha256=sha(build_path),
                telemetry=str(RAW), wrapper_sha256=sha(__file__),
                source_hashes={str(p): v for p, v in HASHES.items()},
                host_inventory=inventory_summary(initial_inventory), runs=[])
    def save():
        (cohort / 'cohort.json').write_text(json.dumps(meta, indent=2) + '\n')
    save()
    print(cohort, flush=True)
    receiver_log = (HERE / 'flow-receiver.log').open('xb')
    receiver = subprocess.Popen([str(RECEIVER), '-addr', '127.0.0.1:43241', '-out', str(RAW)],
                                env=env, stdout=receiver_log, stderr=subprocess.STDOUT)
    meta['receiver_pid'] = receiver.pid
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ready = False
        for _ in range(100):
            assert receiver.poll() is None, 'owned receiver exited'
            try:
                for path in ('/v1/traces', '/v1/logs', '/v1/metrics'):
                    with opener.open(ENDPOINT + path, timeout=1) as response:
                        assert response.status == 200
                ready = True
                break
            except OSError:
                time.sleep(.05)
        assert ready and RAW.exists(), 'receiver not ready'
        assert sha(Path('/proc') / str(receiver.pid) / 'exe') == HASHES[RECEIVER]
        for index, side in enumerate('ABBAAB'):
            before_inventory = inventory()
            assert before_inventory == initial_inventory, 'host inventory drift before sample; retain cohort'
            argv = [sys.executable, str(ADAPTER), '--dagger', str(CLIS[side]),
                    '--module-dir', str(BENCH / 'module'), '--image', RUST,
                    '--samples', '3', '--fresh-engine', ENGINE_REF, '--ripgrep', str(RIPGREP),
                    '--profile-first', '--pinned-source-sync', '--prepare-project-toolchain',
                    '--project-toolchain', str(BENCH / 'fixtures/rust-toolchain-rustfmt.toml')]
            argv += ['--dependency-upgrade', '--profile-dependency-upgrade',
                     '--dependency-first', 'native' if (index // 2) % 2 == 0 else 'dagger']
            sample = dict(index=index, side=side, argv=argv, start_unix_ns=time.time_ns(),
                          host_inventory_before=inventory_summary(before_inventory))
            meta['runs'].append(sample)
            save()
            log = cohort / f'{index}-{side}.log'
            with log.open('xb') as out:
                completed = subprocess.run(argv, cwd=BASE / 'engine-source', env=env,
                                           stdout=out, stderr=subprocess.STDOUT)
            sample.update(end_unix_ns=time.time_ns(), exit_code=completed.returncode, log=str(log))
            roots = [Path(line) for line in log.read_text().splitlines()
                     if line.startswith('/tmp/dagger-rust-loop-') and ' ' not in line]
            assert len(roots) == 1, roots
            sample['root'] = str(roots[0])
            if (roots[0] / 'first-use.json').exists():
                sample['first_use'] = json.loads((roots[0] / 'first-use.json').read_text())
            save()
            print(json.dumps(sample), flush=True)
            assert completed.returncode == 0, 'failed cohort retained'
            after_inventory = inventory()
            sample['host_inventory_after'] = inventory_summary(after_inventory)
            save()
            assert after_inventory == initial_inventory, 'host inventory drift after sample; retain cohort'
            assert all(sha(path)==expected for path,expected in HASHES.items()), 'source/tool drift'
        meta['status'] = 'passed'
    except BaseException as error:
        meta.update(status='failed-or-interrupted', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        receiver.terminate()
        try:
            receiver.wait(timeout=10)
        except subprocess.TimeoutExpired:
            receiver.kill()
            receiver.wait()
        receiver_log.close()
        meta.update(receiver_exit_code=receiver.returncode, end_unix_ns=time.time_ns())
        if RAW.exists():
            meta.update(telemetry_bytes=RAW.stat().st_size, telemetry_sha256=sha(RAW))
        save()
        print(json.dumps(meta), flush=True)

if __name__ == '__main__':
    main()
