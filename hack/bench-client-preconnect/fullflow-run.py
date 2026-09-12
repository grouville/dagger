#!/usr/bin/env python3
"""Three matched CLI preconnection pairs on the same engine image and Cargo workload.

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

HERE = Path('/tmp/dagger-preconnect-flow.xir7YN88')
BASE = Path('/tmp/dagger-rust-current-main-engine.QepteZyL')
BENCH = BASE / 'engine-source/hack/bench-rust-loop'
CLIS = {'A': Path('/tmp/dagger-http-preconnect-main.tRLouH4d/dagger-control'),
        'B': Path('/tmp/dagger-http-preconnect-main.tRLouH4d/dagger-candidate')}
ADAPTER = Path('/tmp/dagger-blob-concurrency.1rQw7cXv/run-cold-mirror-check.py')
CONFIG = Path('/tmp/dagger-blob-concurrency.1rQw7cXv/origin-engine.json')
RECEIVER = Path('/tmp/dagger-rust-perf-sprint.1qnbuQ9j/otlpdump')
RAW = HERE / 'flow-telemetry.jsonl'
ENDPOINT = 'http://127.0.0.1:43227'
ENGINE = 'sha256:848627df950f9d0211436e3210bbbf34ba97f7a1823a528880c5dace238d9a2c'
RUST = 'rust@sha256:39f68a3e8e3ff425f8945ffa91128e60ff930d53e17fbb5214e95824bdd46f1b'
RIPGREP = Path('/tmp/dagger-rust-ripgrep-reference')
HASHES = {
    CLIS['A']: '909120fbf82945488e3b089d527fba0455db1cacdd993bce40bd81071132ddb6',
    CLIS['B']: '23cb7f91c8c346741d349af1b98ba7fd553b160d3f09c56b508bae2fb0e30270',
    BENCH / 'fixtures/ripgrep-bstr-1.12.0.patch': '855d4dfc3bdc090564ac451c41d8d98e44af110f43b78d4ba8b3d00215d642d8',
    ADAPTER: '629c75d15da8d187960ea19e2d79f31e3238079b14a17f4a889e3ce7a3e17c54',
    CONFIG: 'e7b6dc2dc587a7e6405d681590fa23924d7eebb21cdde75d2ec01b8e12910ff5',
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
    cli_source = Path('/tmp/dagger-http-preconnect-main.tRLouH4d/source')
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=cli_source, text=True).strip() == 'ca454ac8870db5c9f5d62573f73ecf03a2849464'
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=cli_source, text=True).strip()
    subprocess.run(['sha256sum', '--check', '/tmp/dagger-http-preconnect-main.tRLouH4d/build-inputs.sha256'], cwd=cli_source, check=True)
    assert not RAW.exists(), 'never append to a prior capture'
    for path, expected in HASHES.items():
        assert sha(path) == expected, str(path)
    env = {key: val for key, val in os.environ.items() if not key.startswith(
        ('GIT_', 'DAGGER_', '_DAGGER_', '_EXPERIMENTAL_DAGGER_', 'OTEL_'))}
    env.pop('DOCKER_CONTEXT', None)
    env.update(DO_NOT_TRACK='1', DNT='1', GIT_OPTIONAL_LOCKS='0',
               DOCKER_HOST='unix:///var/run/docker.sock',
               OTEL_EXPORTER_OTLP_ENDPOINT=ENDPOINT,
               OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=ENDPOINT + '/v1/logs',
               OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=ENDPOINT + '/v1/metrics',
               OTEL_EXPORTER_OTLP_TRACES_LIVE='1')
    def read(*argv, cwd=BASE / 'engine-source'):
        return subprocess.check_output(argv, cwd=cwd, env=env, text=True).strip()
    assert read('git', 'rev-parse', 'HEAD') == 'db9d005c715ac9d146780d783faf7f7b55d23e5e'
    assert not read('git', 'status', '--porcelain')
    assert read('git', 'rev-parse', 'HEAD', cwd=RIPGREP) == '3fce3b5bb0236da2df6d99672afb8a719642eca7'
    assert not read('git', 'status', '--porcelain', cwd=RIPGREP)
    assert read('docker', 'image', 'inspect', ENGINE, '--format', '{{.Id}}') == ENGINE
    native_image = read('docker', 'image', 'inspect', RUST, '--format', '{{.Id}}')
    build_path = Path('/tmp/dagger-stream-reader-lifecycle.w7gTjM09/build/engine-build.json')
    build = json.loads(build_path.read_text())
    assert build['status'] == 'built-and-query-passed', 'real supported tests/build/smoke must pass first'
    assert build['engine_name'] == 'dagger-stream-lifecycle-w7gtjm09'
    assert build['parent'] == 'db9d005c715ac9d146780d783faf7f7b55d23e5e'
    for relative, expected in build['source_hashes'].items():
        assert sha(Path(build['source']) / relative) == expected, relative
    candidate = build['engine_after_smoke']['Image']
    assert read('docker', 'image', 'inspect', candidate, '--format', '{{.Id}}') == candidate
    images = {'A': ENGINE, 'B': candidate}
    assert images['A'] == images['B'], 'only CLI preconnection may differ'
    assert HASHES[CLIS['A']] != HASHES[CLIS['B']]
    cohort = Path(tempfile.mkdtemp(prefix='dagger-rust-cli-flow-ab-'))
    meta = dict(status='running', order='ABBAAB', comparison=True,
                scope='Three matched control-vs-preconnection CLI pairs AB/BA/AB on identical corrected engine image. Fresh independent Cargo/engine states; three repeated source edits and one real bstr upgrade each. First-check/dependency timings profiled; other warm timings unprofiled. Not full installation.',
                cli_paths={side: str(path) for side, path in CLIS.items()},
                cli_sha256={side: HASHES[path] for side, path in CLIS.items()},
                cli_source=str(cli_source), cli_source_commit='ca454ac8870db5c9f5d62573f73ecf03a2849464',
                cli_upstream_main='7c35e6274737acff0f6bd76614abb5e04efa7d12',
                note='Only CLI rebuilt on latest main; retained engine image unchanged. Direct-origin registry override is diagnostic, not a default-route claim.',
                independent_pairs=3, repeated_samples_per_flow=3,
                dependency_upgrade='bstr 1.12.0 -> 1.13.0 once per fresh run',
                preinstalled=['Docker', 'CLI', 'engine image', 'local module', 'native Rust image'],
                image_ids=images, native_image_id=native_image,
                candidate_build=str(build_path), candidate_build_sha256=sha(build_path),
                telemetry=str(RAW), wrapper_sha256=sha(__file__),
                source_hashes={str(p): v for p, v in HASHES.items()}, runs=[])
    def save():
        (cohort / 'cohort.json').write_text(json.dumps(meta, indent=2) + '\n')
    save()
    print(cohort, flush=True)
    receiver_log = (HERE / 'flow-receiver.log').open('xb')
    receiver = subprocess.Popen([str(RECEIVER), '-addr', '127.0.0.1:43227', '-out', str(RAW)],
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
            argv = [sys.executable, str(ADAPTER), '--dagger', str(CLIS[side]),
                    '--module-dir', str(BENCH / 'module'), '--image', RUST,
                    '--samples', '3', '--fresh-engine', images[side], '--ripgrep', str(RIPGREP),
                    '--profile-first', '--pinned-source-sync', '--prepare-project-toolchain',
                    '--project-toolchain', str(BENCH / 'fixtures/rust-toolchain-rustfmt.toml')]
            argv += ['--engine-config', str(CONFIG), '--dependency-upgrade', '--profile-dependency-upgrade',
                     '--dependency-first', 'native' if (index // 2) % 2 == 0 else 'dagger']
            sample = dict(index=index, side=side, argv=argv, start_unix_ns=time.time_ns())
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
