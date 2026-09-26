#!/usr/bin/env python3
"""Constructor policy comparison; no engine work without --run and a reserved slot."""
import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from prepare_measurement import BACKEND, CLI, ENGINE, LAB, OUT, SOURCE, validate_metadata

SENTINEL = 'constructor-cache-api-sentinel'
KINDS = ('listing', 'check')
VARIANTS = ('control', 'constructor')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--phase', choices=('calibrate', 'measure'), default='calibrate')
    p.add_argument('--matrix', choices=('focused', 'full'), default='focused')
    p.add_argument('--profile-port', type=int, default=6172)
    args = p.parse_args()
    if not args.run:
        print(json.dumps({'status': 'prepared only', 'phase': args.phase,
                          'command_count': 12 if args.phase == 'calibrate' else (26 if args.matrix == 'focused' else 46),
                          'edit_boundary': 'distinct fresh comment per command kind; no listing before a measured edit->check'}, indent=2))
        return
    assert (OUT / 'metadata-validation.json').is_file(), 'normal SDK regeneration and validation required'
    apps = {v: OUT / v / 'greetings-api' for v in VARIANTS}
    metadata = {v: validate_metadata(app) for v, app in apps.items()}
    assert metadata['control']['sha256'] == metadata['constructor']['sha256']
    phase_dir = OUT / args.phase
    phase_dir.mkdir(exist_ok=False)
    original = (SOURCE / 'main.go').read_bytes()
    source_manifest = json.loads((OUT / 'manifest.json').read_text())['source_sha256']
    expected = Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt').read_bytes()
    env = dict(os.environ)
    for key in ('SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_PERF_TIMELINE', 'DAGGER_SESSION_PORT',
                'DAGGER_SESSION_TOKEN', '_DAGGER_CLI_TIMING_DIAG', 'DAGGER_CLOUD_BATCH_DIAGNOSTICS', 'DAGGER_CLOUD_URL'):
        env.pop(key, None)
    rows = []
    fixed_paths = ['dagger.toml', 'dagger.lock', BACKEND + '/main.go',
                   BACKEND + '/dagger.gen.go', BACKEND + '/dagger-module.toml']
    fixed_before = {variant: {path: hashlib.sha256((app / path).read_bytes()).hexdigest()
                             for path in fixed_paths} for variant, app in apps.items()}
    (phase_dir / 'provenance.json').write_text(json.dumps({
        'matrix': args.matrix, 'engine': ENGINE, 'cli': CLI,
        'telemetry': 'normal direct Cloud; no local relay',
        'metadata': metadata, 'fixed_inputs_before': fixed_before,
        'boundary': 'retained experimental TS-static engine; full fresh CLI process to exit',
    }, indent=2) + '\n')

    def dump(path, allow_missing=False):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.profile_port}/debug/wcprof/dump?flush=true', timeout=20) as r:
                path.write_bytes(r.read())
        except urllib.error.HTTPError as error:
            if not (allow_missing and error.code == 503):
                raise

    def pressure():
        return int(Path('/proc/pressure/io').read_text().splitlines()[1].rsplit('=', 1)[1])

    def run(variant, label, kind='check', profile=False,
            tests=('TestSelectGreeting', 'TestFormatResponse'), expected_failure=False, require_six=False):
        dest = phase_dir / label
        dest.mkdir(parents=True, exist_ok=False)
        command = [CLI, '--engine', 'container://' + ENGINE]
        if profile:
            dump(dest / 'prior.wcprof', True)
            command += ['--profile']
        if kind == 'listing':
            command += ['check', '-l', '--all']
        else:
            command += ['check', '--generated=false', 'go/modules/tests/run', '--go-module=.']
            command += ['--go-test=' + name for name in tests]
        io_start = pressure()
        started_unix_ns = time.time_ns() if profile else None
        started = time.perf_counter()
        result = subprocess.run(command, cwd=apps[variant], env=env, capture_output=True, timeout=900)
        elapsed = time.perf_counter() - started
        exited_unix_ns = time.time_ns() if profile else None
        io_end = pressure()
        (dest / 'stdout.txt').write_bytes(result.stdout)
        (dest / 'stderr.txt').write_bytes(result.stderr)
        output = re.sub(r'\x1b\[[0-9;]*m', '', (result.stdout + result.stderr).decode(errors='replace'))
        row = {'variant': variant, 'label': label, 'kind': kind, 'command': command,
               'seconds': elapsed, 'exit_code': result.returncode, 'profile': profile,
               'expected_failure': expected_failure, 'io_full_stall_seconds': (io_end - io_start) / 1e6,
               'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
               'source_sha256': hashlib.sha256((apps[variant] / 'main.go').read_bytes()).hexdigest()}
        if profile:
            row['started_unix_ns'] = started_unix_ns
            row['exited_unix_ns'] = exited_unix_ns
            row['profile_clock_note'] = 'host CLI wall timestamps aligned with wcprof epoch_unix_nano; same-host wall-clock alignment assumes no clock step'
        rows.append(row)
        (phase_dir / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(json.dumps(row), flush=True)
        if profile:
            dump(dest / 'run.wcprof')
        if expected_failure:
            assert result.returncode != 0 and SENTINEL in output, (row, output[-4000:])
        elif kind == 'listing':
            assert result.returncode == 0 and result.stdout == expected, (row, output[-4000:])
        else:
            assert result.returncode == 0 and re.search(r'== CHECKS ==.*\b1 passed\b', output), (row, output[-4000:])
            if require_six:
                assert re.search(r'\b6 passed\b', output) and not re.search(r'\b[1-9][0-9]* skipped\b', output), (row, output[-4000:])

    def edit(label):
        data = original + ('\n// Constructor cache measurement ' + label + '.\n').encode()
        for app in apps.values():
            (app / 'main.go').write_bytes(data)

    try:
        if args.phase == 'calibrate':
            for i in range(2):
                for kind in KINDS:
                    for variant in VARIANTS:
                        run(variant, f'warmup/{i}-{kind}-{variant}', kind)
            for kind in KINDS:
                for variant in VARIANTS:
                    run(variant, f'profiles/warm-{kind}-{variant}', kind, profile=True)
        else:
            assert (OUT / 'calibrate/results.json').is_file(), 'inspect warm calibration profiles before timing'
            for i in range(5):
                for kind in KINDS if args.matrix == 'full' else ('listing',):
                    for variant in VARIANTS if i % 2 == 0 else tuple(reversed(VARIANTS)):
                        run(variant, f'warm/{i}-{kind}-{variant}', kind)
            for i in range(5):
                for kind in KINDS if args.matrix == 'full' else ('check',):
                    # Each kind gets distinct bytes, so edit->check cannot reuse
                    # a constructor already evaluated by an earlier listing.
                    edit(f'fresh-{kind}-{i}')
                    for variant in VARIANTS if i % 2 == 0 else tuple(reversed(VARIANTS)):
                        run(variant, f'edits/{i}-{kind}-{variant}', kind)
            edit('profile-fresh-check')
            for variant in VARIANTS:
                run(variant, f'profiles/edit-check-{variant}', profile=True)
            needle = b'greeting.Greeting)'
            assert original.count(needle) == 1
            for variant in VARIANTS:
                (apps[variant] / 'main.go').write_bytes(original.replace(needle, b'greeting.Greeting+"-' + SENTINEL.encode() + b'")'))
                run(variant, f'correctness/{variant}-api-sentinel', tests=('TestE2EGreetingByLanguage',), expected_failure=True)
                (apps[variant] / 'main.go').write_bytes(original + b'\n// Constructor cache restored HTTP behavior.\n')
                run(variant, f'correctness/{variant}-restored-full', tests=(), require_six=True)
            summary = {phase: {kind: {variant: {
                'samples': values,
                'median_seconds': statistics.median(values),
            } for variant in VARIANTS
                if (values := [r['seconds'] for r in rows if r['variant'] == variant and r['kind'] == kind and r['label'].startswith(phase + '/')])}
                for kind in KINDS} for phase in ('warm', 'edits')}
            (phase_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    finally:
        for app in apps.values():
            (app / 'main.go').write_bytes(original)
        unchanged = {path: hashlib.sha256((SOURCE / path).read_bytes()).hexdigest() == want
                     for path, want in source_manifest.items()}
        (phase_dir / 'source-unchanged.json').write_text(json.dumps(unchanged, indent=2) + '\n')
        assert all(unchanged.values()), unchanged
        fixed_unchanged = {variant: {path: hashlib.sha256((apps[variant] / path).read_bytes()).hexdigest() == digest
                                    for path, digest in paths.items()} for variant, paths in fixed_before.items()}
        (phase_dir / 'fixed-inputs-unchanged.json').write_text(json.dumps(fixed_unchanged, indent=2) + '\n')
        if args.phase == 'measure':
            assert all(all(paths.values()) for paths in fixed_unchanged.values()), fixed_unchanged


if __name__ == '__main__':
    main()
