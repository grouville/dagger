import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'package-metadata-validation'
root.mkdir(exist_ok=False)
source = root / 'workspace'
source.mkdir()
toolchain = Path('/tmp/rcexp-rustup/toolchains/1.77.2-x86_64-unknown-linux-gnu/bin')
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276',
           RUST_CACHE_BENCH_CLI=str(base / 'dagger-artifact-list-buffered'),
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(base / 'dagger-artifact-workspace-before'))
cargo_env = dict(os.environ, RUSTC=str(toolchain / 'rustc'), RUSTDOC=str(toolchain / 'rustdoc'))
for key in ['RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER']:
    cargo_env.pop(key, None)


def write(path, text):
    filename = source / path
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(text)


write('Cargo.toml', '[workspace]\nmembers = ["app", "shared"]\nresolver = "2"\n')
write('app/Cargo.toml', '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n[dependencies]\nshared = { path = "../shared" }\n')
write('app/src/lib.rs', 'pub fn value() -> u64 { shared::value() + 1 }\n')
write('shared/Cargo.toml', '[package]\nname = "shared"\nversion = "0.1.0"\nedition = "2021"\n')
write('shared/src/lib.rs', 'pub fn value() -> u64 { 1 }\n')
subprocess.run([str(toolchain/'cargo'), 'generate-lockfile', '--offline'],
               cwd=source, env=cargo_env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def debug(route, data=None):
    return urllib.request.urlopen(urllib.request.Request(
        'http://127.0.0.1:16104/debug/' + route, data=data), timeout=30)


def invoke(label, expected_execs, expect_failure=False):
    oracle = subprocess.run([str(toolchain/'cargo'), 'metadata', '--offline', '--locked',
                             '--no-deps', '--format-version=1'],
                            cwd=source, env=cargo_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert bool(oracle.returncode) == expect_failure, (label, oracle.stderr.decode())
    expected = sorted(package['name'] for package in json.loads(oracle.stdout)['packages']) if not expect_failure else []
    with debug('wcprof/enabled', b'on'):
        pass
    with debug('wcprof/dump') as response:
        while response.read(1048576):
            pass
    command = ['python3', str(base/'local_cli.py'), 'api', 'with-session', '--',
               str(base/'rust-packages-cache-inspect'), '-native-cache',
               '-cache-key', 'metadata-validation-v1', '-source', str(source)]
    if not expect_failure:
        command += ['-expected', ','.join(expected)]
    try:
        with (root/(label+'.log')).open('w') as output:
            result = subprocess.run(command, cwd='/tmp/dagger-rust-package-metadata-cache',
                                    env=env, stdout=output, stderr=subprocess.STDOUT)
    finally:
        with debug('wcprof/enabled', b'off'):
            pass
        with debug('wcprof/dump') as response, (root/(label+'.ndjson')).open('wb') as output:
            while chunk := response.read(1048576):
                output.write(chunk)
    assert bool(result.returncode) == expect_failure, label
    with (root/(label+'.ndjson')).open() as stream:
        header = json.loads(next(stream))
        executions = [op for op in map(json.loads, stream) if op.get('e')=='op' and op.get('k')=='exec']
    assert not header['dropped_events'] and not header.get('open_ops'), label
    assert len(executions) == expected_execs, (label, len(executions), expected_execs)
    print('PASS', label, 'packages', expected, 'executions', len(executions), flush=True)


try:
    invoke('cold', 2)
    write('app/src/lib.rs', 'this is invalid Rust but metadata does not compile it\n')
    invoke('rust-content-edit', 1)
    write('app/src/bin/new.rs', 'fn main() {}\n')
    invoke('new-target', 2)
    write('app/Cargo.toml', (source/'app/Cargo.toml').read_text().replace('name = "app"', 'name = "renamed_app"'))
    invoke('renamed-package', 2)
    write('app/src/lib.rs', 'pub fn value() -> u64 { 2 }\n')
    invoke('renamed-package-rust-edit', 1)
    (source/'Cargo.lock').write_text((source/'Cargo.lock').read_text() + '\n# configuration edit\n')
    invoke('lock-edit', 2)
    write('app/manifest.rs', (source/'app/Cargo.toml').read_text())
    (source/'app/Cargo.toml').unlink()
    (source/'app/Cargo.toml').symlink_to('manifest.rs')
    invoke('symlinked-manifest', 2)
    write('app/manifest.rs', (source/'app/manifest.rs').read_text().replace('renamed_app', 'linked_app'))
    invoke('symlink-target-contents', 2)
    write('app/alternate.rs', 'pub fn value() -> u64 { 3 }\n')
    (source/'app/src/lib.rs').unlink()
    (source/'app/src/lib.rs').symlink_to('../alternate.rs')
    invoke('source-symlink', 2)
    write('app/other.rs', 'pub fn value() -> u64 { 4 }\n')
    invoke('other-rust-path', 2)
    (source/'app/src/lib.rs').unlink()
    (source/'app/src/lib.rs').symlink_to('../other.rs')
    invoke('retargeted-source-symlink', 2)
    write('.cargo/config.toml', '[build]\njobs = 2\n')
    invoke('cargo-config-fallback', 2)
    write('app/other.rs', 'pub fn value() -> u64 { 5 }\n')
    invoke('cargo-config-rust-edit', 2)
    (source/'.cargo/config.toml').unlink()
    (source/'.cargo').rmdir()
    write('shared/Cargo.toml', '[package]\nname = 42\n')
    invoke('invalid-manifest', 2, expect_failure=True)
finally:
    with debug('wcprof/enabled', b'off'):
        pass
