#!/usr/bin/env python3
"""Three matched Unix socket readiness engine pairs driven by one frozen CLI.

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
ADAPTER_OWNER = Path("/tmp/dagger-cli-readiness-auto.C70FUvMf")
ENGINE_REFS = {
    'A': 'localhost/dagger-stream-close-order-6u5eynjb:latest',
    'B': 'localhost/dagger-unix-readiness-ufjy9dsi:latest',
}
ENGINE_SOURCES = {
    'A': Path('/tmp/dagger-stream-close-order.6U5EYNjb/engine-source'),
    'B': HERE / 'engine-source',
}
ENGINE_PARENT = '503d3410ef3df63fa6bc7a55c5c2453c4951c2c2'
UPSTREAM_MAIN = '7c35e6274737acff0f6bd76614abb5e04efa7d12'
CONTROL_IMAGE = 'sha256:1fb3565bb5bac059d2a89e52e231203befe215ba4396ea40c93393b19f77aeb0'
CANDIDATE_IMAGE = 'sha256:5d660298fd273eec4facabca4b1ecaf56cac7bc2342aaf3eec6a6d26ff1bb8da'
ENGINE_CHANGES = {'cmd/dialstdio/main.go', 'cmd/dialstdio/main_test.go', 'cmd/dialstdio/stdio_test.go'}
BASE = Path('/tmp/dagger-rust-current-main-engine.QepteZyL')
BENCH = BASE / 'engine-source/hack/bench-rust-loop'
CLI = CLI_OWNER / 'dagger-candidate'
CLIS = {'A': CLI, 'B': CLI}
ADAPTER = ADAPTER_OWNER / 'run-cli-provision-check.py'
RECEIVER = Path('/tmp/dagger-rust-perf-sprint.1qnbuQ9j/otlpdump')
RAW = HERE / 'flow-telemetry.jsonl'
ENDPOINT = 'http://127.0.0.1:43242'
RUST = 'rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b'
RIPGREP = Path('/tmp/dagger-rust-ripgrep-reference')
HASHES = {
    HERE / 'build-candidate.py': '874edce662a06e87f4772f5af893e44ee14abf5c27e9d89d97697cd481a6e482',
    HERE / 'engine-builds/builds.json': '4036040ebb38da27739225fdf2ab13183065ac4868e198dd7aaf4b8c0a00db54',
    HERE / 'test-docker-lifecycle.py': '98530cb41f449f18afff85e185b5d4e32e0f184b899b69effd391e9a56f94c02',
    HERE / 'docker-lifecycle.json': '8be76102055593e57e3afb41712b4e76da9bf60d629c2445311d35e8f75d384f',
    CLI: '6a5b01851eda5ebb122e29c8ac43eba35d0097b2b1cedb2d183a1ffc71c37cad',
    CLI_OWNER / 'build-inputs.sha256': 'e617c45618290bbe31555c4f6e5e0ceae86b3756451d9b51d03d55f99e1c80f8',
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
    cli_source = Path('/tmp/dagger-container-inventory-publish.78Tj718Q/repo')
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cli_source, text=True).strip() == '40ad085ad7e5af0683da3e2b9871300ce0de3083'
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=cli_source, text=True).strip()
    subprocess.run(['sha256sum', '--check', str(CLI_OWNER / 'build-inputs.sha256')], cwd=cli_source, check=True)
    assert not RAW.exists(), 'never append to a prior capture'
    for path, expected in HASHES.items():
        assert sha(path) == expected, str(path)
    # Freeze the controller/analysis before capture, not after seeing outcomes.
    for name in ('run-fullflow.py','analyze-fullflow.py','summarize-fullflow.py','phase-summary.py','audit-ordinary.py'):
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
    build_path = HERE / 'engine-builds/builds.json'
    build = json.loads(build_path.read_text())
    assert build['status'] == 'built-and-query-passed', 'candidate build/test/smoke must finish before capture'
    assert build['parent'] == ENGINE_PARENT and build['upstream_main'] == UPSTREAM_MAIN
    assert build['cli'] == str(CLI) and build['cli_sha256'] == HASHES[CLI]
    assert build['controller_sha256'] == sha(HERE / 'build-candidate.py')
    assert set(build['differences']) == ENGINE_CHANGES
    assert build['source_roots'] == {side: str(path) for side, path in ENGINE_SOURCES.items()}
    previous_path = Path('/tmp/dagger-stream-close-order.6U5EYNjb/engine-builds/builds.json')
    assert build['previous_build'] == str(previous_path)
    assert build['previous_build_sha256'] == sha(previous_path) == '0475e9f6ac649a827b154491d0b45ce3ff58e38eb287cbcb71fc8ebf09f2ea23'
    previous = json.loads(previous_path.read_text())
    assert previous['status'] == 'built-and-query-passed'
    assert previous['parent'] == ENGINE_PARENT and previous['upstream_main'] == UPSTREAM_MAIN
    assert build['source_hashes']['A'] == previous['source_hashes']['B']
    old = build['source_hashes']['A']
    changed = build['source_hashes']['B']
    assert set(changed) == set(old) | ENGINE_CHANGES
    assert all(changed[path] == expected for path, expected in old.items())
    for path in (build_path, previous_path, HERE / 'build-candidate.py'):
        HASHES[path] = sha(path)
    HASHES[ENGINE_SOURCES['A'] / 'cmd/dialstdio/main.go'] = 'b83c1aff04f5f0b95e6788dcf69d4c3dbbb08b49aa3efb662e78fdcfd56183c1'
    assert sha(ENGINE_SOURCES['A'] / 'cmd/dialstdio/main.go') == HASHES[ENGINE_SOURCES['A'] / 'cmd/dialstdio/main.go']
    for relative in ENGINE_CHANGES:
        assert changed[relative] == sha(HERE / 'source' / relative)
        HASHES[HERE / 'source' / relative] = changed[relative]
    images = {}
    assert len(build['builds']) == 2
    for entry in build['builds']:
        side = entry['side']
        assert side in ENGINE_SOURCES and side not in images
        source = ENGINE_SOURCES[side]
        assert entry['source'] == str(source) and entry['status'] == 'built-and-query-passed'
        assert entry['commands'] and all(command['exit_code'] == 0 for command in entry['commands'])
        assert read('git', 'rev-parse', 'HEAD', cwd=source) == ENGINE_PARENT
        assert read('git', 'merge-base', UPSTREAM_MAIN, 'HEAD', cwd=source) == UPSTREAM_MAIN
        assert not read('git', 'diff', '--check', cwd=source)
        paths = set(read('git', 'diff', 'HEAD', '--name-only', cwd=source).splitlines())
        paths.update(read('git', 'ls-files', '--others', '--exclude-standard', cwd=source).splitlines())
        assert paths == set(build['source_hashes'][side]), 'unexpected engine-source difference'
        for relative, expected in build['source_hashes'][side].items():
            assert sha(source / relative) == expected, relative
            HASHES[source / relative] = expected
        images[side] = entry['engine_after_smoke']['Image']
        assert read('docker', 'image', 'inspect', images[side], '--format', '{{.Id}}') == images[side]
        assert read('docker', 'image', 'inspect', ENGINE_REFS[side], '--format', '{{.Id}}') == images[side]
    assert images == {'A': CONTROL_IMAGE, 'B': CANDIDATE_IMAGE} and images['A'] != images['B']
    lifecycle_path = HERE / 'docker-lifecycle.json'
    lifecycle = json.loads(lifecycle_path.read_text())
    assert lifecycle['status'] == 'passed' and lifecycle['build_sha256'] == HASHES[build_path]
    assert lifecycle['script_sha256'] == HASHES[HERE / 'test-docker-lifecycle.py']
    candidate = next(entry for entry in build['builds'] if entry['side'] == 'B')
    assert lifecycle['engine']['Image'] == images['B']
    assert lifecycle['engine']['Id'] == candidate['engine_after_smoke']['Id']
    assert len(lifecycle['cases']) == 2 and all(case['passed'] for case in lifecycle['cases'])
    assert [(case['close_local_client'], case['timeout_seconds']) for case in lifecycle['cases']] == [(False, 1), (True, 5)]
    assert CLIS['A'] == CLIS['B'] and len({HASHES[path] for path in CLIS.values()}) == 1
    for line in (CLI_OWNER / 'build-inputs.sha256').read_text().splitlines():
        expected, relative = line.split(maxsplit=1)
        HASHES[cli_source / relative] = expected
    cohort = Path(tempfile.mkdtemp(prefix='dagger-rust-unix-readiness-ab-'))
    meta = dict(status='running', order='ABBAAB', comparison=True,
                scope='Three matched control-vs-Unix-socket-readiness engine pairs AB/BA/AB with the identical inventory/readiness CLI, verified-stream implementation, official gzip Rust image and default registry configuration. CLI itself provisions each new engine using image+docker with cleanup disabled solely to preserve unrelated engines. Preinstalled engine images; full first CLI includes provisioning. Post-timer profile/cache retrieval uses a helper copied only after the first CLI exits. Fresh independent Cargo/engine states; three repeated source edits and one real bstr upgrade each. First-check/dependency timings profiled; other warm timings omit --profile but export local OTLP. Not full installation.',
                cli_paths={side: str(path) for side, path in CLIS.items()},
                cli_sha256={side: HASHES[path] for side, path in CLIS.items()},
                cli_source=str(cli_source), cli_source_commit='40ad085ad7e5af0683da3e2b9871300ce0de3083',
                engine_source_roots={side: str(path) for side, path in ENGINE_SOURCES.items()},
                engine_source_parent=ENGINE_PARENT, engine_differences=sorted(ENGINE_CHANGES),
                cli_upstream_main='7c35e6274737acff0f6bd76614abb5e04efa7d12',
                note='Same frozen CLI binary on both sides, including validated client readiness and Docker inventory filtering. B changes only the engine dial-stdio Unix socket connection helper plus two tests; positive timeout retries ENOENT/ECONNREFUSED within one deadline. Nonpositive behavior, established stdio streams, image streaming, module actions, session/cache ownership and global gRPC retry policy remain unchanged. Host inventory is guarded outside timers. Default registry route, no custom config or prewarming. Docker/CLI/engine images/module/native image preinstalled; host page/CDN caches not purged. All outcomes remain; no required speedup or startup-delay injection.',
                independent_pairs=3, repeated_samples_per_flow=3,
                engine_provisioning='ordinary-image-driver-inside-cli',
                engine_references=ENGINE_REFS, diagnostic_helper='post-first-CLI copy, loopback-only debug retrieval',
                dependency_upgrade='bstr 1.12.0 -> 1.13.0 once per fresh run',
                preinstalled=['Docker', 'CLI', 'engine image', 'local module', 'native Rust image'],
                image_ids=images, native_image_id=native_image,
                candidate_build=str(build_path), candidate_build_sha256=sha(build_path),
                lifecycle_validation=str(lifecycle_path), lifecycle_validation_sha256=sha(lifecycle_path),
                lifecycle_scope='Separate post-build owned-engine validation, outside all workload timers. Local Docker client closure is not immediate container-exec cancellation; the disconnected helper remains bounded by its existing five-second timeout.',
                telemetry=str(RAW), wrapper_sha256=sha(__file__),
                source_hashes={str(p): v for p, v in HASHES.items()},
                host_inventory=inventory_summary(initial_inventory), runs=[])
    def save():
        (cohort / 'cohort.json').write_text(json.dumps(meta, indent=2) + '\n')
    save()
    print(cohort, flush=True)
    receiver_log = (HERE / 'flow-receiver.log').open('xb')
    receiver = subprocess.Popen([str(RECEIVER), '-addr', '127.0.0.1:43242', '-out', str(RAW)],
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
            assert read('docker', 'image', 'inspect', ENGINE_REFS[side], '--format', '{{.Id}}') == images[side]
            argv = [sys.executable, str(ADAPTER), '--dagger', str(CLIS[side]),
                    '--module-dir', str(BENCH / 'module'), '--image', RUST,
                    '--samples', '3', '--fresh-engine', ENGINE_REFS[side], '--ripgrep', str(RIPGREP),
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
