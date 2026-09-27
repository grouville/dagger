"""Four LOCAL diagnostic calls: primer/profile/primer/profile, no speedup claim."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

H = Path(__file__).resolve().parent
LAB = Path('/tmp/collections-perf/engine-allocation-round2')
sys.path.insert(0, str(H))
from lifecycle import EngineLifecycle, ANSI, x

CAP = 4
EXPECTED_MODULE = '0b12a6f3fe091f5896c19f642e2074593dceca554275b150a450e06732d640be'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def normalized(raw):
    return [b' '.join(line.split()) for line in ANSI.sub(b'', raw).splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'prepared_only': True, 'local_cli_cap': CAP, 'cloud_calls': 0, 'sequence': ['primer', 'profile', 'primer', 'profile'], 'command': ['check', '-l', '--all'], 'scope': 'Existing behavior plus profile-only labels; no ordinary A/B or speedup claim.'}))
        return
    frozen = json.loads((H / 'frozen-runtime-inputs.json').read_text())
    for path, want in frozen['source_sha256'].items():
        assert sha(path) == want, path
    assert sha(H / 'frozen-engine-manifest.json') == frozen['engine_manifest_sha256']
    candidate = Path(frozen['candidate_module'])
    assert sha(candidate) == EXPECTED_MODULE
    original = LAB / 'greetings'
    initial = json.loads((LAB / 'withfile-v1/prepared.json').read_text())['input_sha256']
    assert all(sha(original / name) == want for name, want in initial.items())
    workspace = H / 'greetings-v1'
    output = H / 'results-v1'
    assert not workspace.exists() and not output.exists() and not (H / 'summary-v1.json').exists()
    for name in initial:
        dest = workspace / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original / name, dest)
    subprocess.run(['git', 'init', '-q', str(workspace)], check=True, timeout=10)
    subprocess.run(['git', '-C', str(workspace), 'add', '-f', '.'], check=True, timeout=10)
    originals = {name: (workspace / name).read_bytes() for name in ('dagger.toml', 'dagger.lock')}
    local = workspace / '.dagger/perf-go'
    local.mkdir(parents=True)
    (local / 'go.dang').write_bytes(candidate.read_bytes())
    (local / 'dagger-module.toml').write_bytes((H / 'module-manifest.toml').read_bytes())
    config = originals['dagger.toml']
    remote = b'source = "github.com/dagger/go@collections"'
    base = b'base = "dag://backend/go-test-base"'
    assert config.count(remote) == 1 and config.count(base) == 1
    config = config.replace(remote, b'source = ".dagger/perf-go"').replace(base, b'baseAddress = "dag://backend/go-test-base"')
    (workspace / 'dagger.toml').write_bytes(config)
    expected_files = {name: want for name, want in initial.items() if name != 'dagger.lock'}
    for name in ('dagger.toml', '.dagger/perf-go/go.dang', '.dagger/perf-go/dagger-module.toml'):
        expected_files[name] = sha(workspace / name)
    golden = normalized(Path(frozen['checks_golden']).read_bytes())
    assert len(golden) == 14
    facts = {'local_cli_cap': CAP, 'cloud_calls': 0, 'sequence': ['primer', 'profile', 'primer', 'profile'], 'scope': 'Profile-only diagnosis of unchanged check listing; no latency comparison or inferred saving.', 'validated_commands': 0}

    def guard():
        assert {k: v for k, v in x.fixture_hashes(workspace).items() if k != 'dagger.lock'} == expected_files
        assert all(sha(original / name) == want for name, want in initial.items())

    def validate(row, stdout, stderr):
        return row['exit_code'] == 0 and normalized(stdout) == golden

    try:
        guard()
        with EngineLifecycle(output, CAP) as engine:
            for index, label in enumerate(facts['sequence']):
                engine.run(['check', '-l', '--all'], workspace, validate, '%d-%s' % (index, label), profile=label == 'profile', timeout=180)
                guard()
            assert len(engine.rows) == CAP and all(row['correct'] for row in engine.rows)
            facts['validated_commands'] = CAP
    finally:
        for name, body in originals.items():
            (workspace / name).write_bytes(body)
        if local.exists():
            shutil.rmtree(local)
        facts['copied_fixture_restored'] = x.fixture_hashes(workspace) == initial
        facts['original_fixture_untouched'] = all(sha(original / name) == want for name, want in initial.items())
        facts['module_sha256'] = EXPECTED_MODULE
        facts['engine_manifest_sha256'] = frozen['engine_manifest_sha256']
        x.write(H / 'summary-v1.json', facts)
        assert facts['copied_fixture_restored'] and facts['original_fixture_untouched']


if __name__ == '__main__':
    main()
