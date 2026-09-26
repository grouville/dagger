#!/usr/bin/env python3
"""Prepared execution matrix. Default is a dry run; engines are caller-managed."""
from pathlib import Path
import argparse, hashlib, json, os, re, shutil, statistics, subprocess, time, urllib.error, urllib.request

SENTINEL = 'execution-perf-invalidation-sentinel'
TESTS = {
    'single': ['TestFormatResponse'],
    'pair': ['TestSelectGreeting', 'TestFormatResponse'],
    'control': ['TestSelectGreeting'],
    'full-module': [],
}

def command(cli, engine, case, listing=False, profile=False):
    cmd = [cli, '--engine', 'container://' + engine]
    if profile:
        cmd += ['--profile']
    cmd += ['check', '--generated=false', 'go/modules/tests/run', '--go-module=.']
    cmd += ['--go-test=' + name for name in TESTS[case]]
    if listing:
        cmd += ['-l', '--all']
    return cmd

def sha(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='/tmp/collections-perf/normal-baseline/greetings-split')
    parser.add_argument('--cli', default='/tmp/collections-perf/rebase-main/dagger')
    parser.add_argument('--engine', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile-port', type=int)
    parser.add_argument('--warm-runs', type=int, default=8)
    parser.add_argument('--include-full-module', action='store_true', help='Also run all six root tests, including four real HTTP e2e tests')
    parser.add_argument('--profile-first', action='store_true', help='Profile first execution separately; never use its timing as an unprofiled cold measurement')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    cases = ['single', 'pair'] + (['full-module'] if args.include_full_module else [])
    if args.profile_first and not args.profile_port:
        parser.error('--profile-first requires --profile-port')
    if not args.run:
        print(json.dumps({'status': 'prepared, not executed', 'commands': {c: command(args.cli, args.engine, c) for c in cases}, 'notes': ['Engine must already be running and exclusively assigned.', 'First execution on this retained engine is not a cold-start claim.', 'Warm timings may reuse Dagger or Go test results; profiles distinguish actual process execution.', 'Source edits affect only an isolated copy and are restored.']}, indent=2))
        return
    source = Path(args.app).resolve()
    out = args.output.resolve()
    if out == source or source in out.parents:
        parser.error('--output must be outside the original app')
    out.mkdir(parents=True, exist_ok=False)
    running = subprocess.check_output(['docker', 'inspect', '--format', '{{.State.Running}}', args.engine], text=True).strip()
    if running != 'true':
        raise RuntimeError('Caller must start and exclusively reserve the requested engine')
    app = out / 'workspace' / 'greetings-api'
    shutil.copytree(source, app, symlinks=True)
    originals = {p: (app / p).read_bytes() for p in ('main.go', 'main_test.go')}
    source_hashes = {p: sha((source / p).read_bytes()) for p in originals}
    env = dict(os.environ)
    for key in ('SSH_AUTH_SOCK', 'CPUPROFILE', 'DAGGER_CLOUD_BATCH_DIAGNOSTICS'):
        env.pop(key, None)
    rows = []
    provenance = {'app_source': str(source), 'isolated_copy': str(app), 'source_hashes': source_hashes, 'cli': args.cli, 'cli_sha256': sha(Path(args.cli).read_bytes()), 'engine': args.engine, 'config_sha256': sha((app / 'dagger.toml').read_bytes()), 'lock_before_sha256': sha((app / 'dagger.lock').read_bytes()), 'engine_state': 'caller-managed retained engine; no cold-state guarantee', 'command_contract': 'Full fresh CLI process, configured base/service retained, telemetry enabled, process exit included. No forced cache bypass.'}
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def pressure():
        try:
            return {line.split()[0]: int(line.split()[-1].split('=')[1]) for line in Path('/proc/pressure/io').read_text().splitlines()}
        except (OSError, ValueError):
            return {}

    def dump(path, allow_unstarted=False):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.profile_port}/debug/wcprof/dump?flush=true', timeout=20) as response:
                path.write_bytes(response.read())
        except urllib.error.HTTPError as error:
            if not (allow_unstarted and error.code == 503):
                raise

    def run(case, label, listing=False, fail=False, profile=False):
        dest = out / label
        dest.mkdir(parents=True, exist_ok=False)
        cmd = command(args.cli, args.engine, case, listing, profile)
        if profile:
            dump(dest / 'prior-events.wcprof', allow_unstarted=True)
        before = pressure()
        start = time.perf_counter()
        result = subprocess.run(cmd, cwd=app, env=env, capture_output=True, timeout=900)
        elapsed = time.perf_counter() - start
        after = pressure()
        (dest / 'stdout.txt').write_bytes(result.stdout)
        (dest / 'stderr.txt').write_bytes(result.stderr)
        text = (result.stdout + result.stderr).decode(errors='replace')
        row = {'case': case, 'label': label, 'command': cmd, 'seconds': elapsed, 'exit_code': result.returncode, 'profile': profile, 'expected_failure': fail, 'stdout_sha256': sha(result.stdout), 'io_full_stall_seconds': (after.get('full', 0) - before.get('full', 0)) / 1e6}
        rows.append(row)
        (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
        print(json.dumps(row), flush=True)
        if profile:
            dump(dest / 'run.wcprof')
        if fail:
            assert result.returncode != 0 and SENTINEL in text, (label, 'Expected selected test failure with sentinel, not infrastructure failure')
        else:
            assert result.returncode == 0, (label, text[-3000:])
            if listing:
                lines = result.stdout.decode().splitlines()
                expected = TESTS[case] or ['TestE2ERandomGreeting', 'TestE2EGreetingByLanguage', 'TestE2EUnknownLanguage', 'TestE2ECORS', 'TestSelectGreeting', 'TestFormatResponse']
                assert len(lines) == len(expected), (label, lines)
                assert all(sum(name in line for line in lines) == 1 for name in expected), (label, lines)
                assert all('dag+check://go/modules/tests/run' in line for line in lines), (label, lines)
            else:
                clean = re.sub(r'\x1b\[[0-9;]*m', '', text)
                assert re.search(r'== CHECKS ==.*\b1 passed\b', clean), (label, 'Expected one grouped Check result', clean[-1500:])

    try:
        for case in cases:
            run(case, f'preflight/{case}', listing=True)
        for case in cases:
            run(case, f'first-execution/{case}', profile=args.profile_first)
        for repeat in range(2):
            for case in cases:
                run(case, f'warmup/{repeat}-{case}')
        for repeat in range(args.warm_runs):
            for case in cases if repeat % 2 == 0 else reversed(cases):
                run(case, f'warm/{repeat}-{case}')
        (app / 'main.go').write_bytes(originals['main.go'] + b'\n// Execution benchmark: ordinary source edit.\n')
        run('single', 'edits/production-comment')
        (app / 'main.go').write_bytes(originals['main.go'])
        run('single', 'edits/production-restore')
        needle = b'func TestFormatResponse(t *testing.T) {\n'
        assert originals['main_test.go'].count(needle) == 1
        changed = originals['main_test.go'].replace(needle, needle + ('\tt.Fatal("' + SENTINEL + '")\n').encode())
        (app / 'main_test.go').write_bytes(changed)
        run('single', 'correctness/selected-fails', fail=True)
        run('control', 'correctness/unselected-failure-ignored')
        run('pair', 'correctness/batch-propagates-failure', fail=True)
        (app / 'main_test.go').write_bytes(originals['main_test.go'])
        run('single', 'correctness/restored-passes')
        if args.profile_port:
            for case in cases:
                run(case, f'profiles/warm-{case}', profile=True)
            (app / 'main.go').write_bytes(originals['main.go'] + b'\n// Execution profile: fresh production edit.\n')
            run('pair', 'profiles/edited-pair', profile=True)
    finally:
        for name, original in originals.items():
            (app / name).write_bytes(original)
        restoration = {'isolated_copy': {name: sha((app / name).read_bytes()) == sha(data) for name, data in originals.items()}, 'original_app': {name: sha((source / name).read_bytes()) == digest for name, digest in source_hashes.items()}}
        (out / 'restoration.json').write_text(json.dumps(restoration, indent=2) + '\n')
        assert all(all(values.values()) for values in restoration.values()), restoration
    summary = {case: {'median_seconds': statistics.median(r['seconds'] for r in rows if r['case'] == case and r['label'].startswith('warm/')), 'samples': [r['seconds'] for r in rows if r['case'] == case and r['label'].startswith('warm/')]} for case in cases}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

if __name__ == '__main__':
    main()
