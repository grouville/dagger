"""Recheck #14184 on current main, through a complete fresh CLI process.

Run one workload at a time. Engines and volumes are retained. Source/output
reset is outside timing; generation, export and session cleanup are inside.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import signal
import statistics
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--pairs', type=int, default=6)
parser.add_argument('--sizes', type=int, nargs='+', default=[32, 67108864])
parser.add_argument('--profile', action='store_true')
parser.add_argument('--private-source', action='store_true', help='Copy freshly created private files, as the PR regression does')
args = parser.parse_args()
engines = json.loads((ROOT / 'engines.json').read_text())
samples = []
logdir = ROOT / (('profiles' if args.profile else 'logs') + ('-private-source' if args.private_source else ''))
logdir.mkdir(exist_ok=True)


def digest(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def metadata(root):
    return {str(f.relative_to(root)): digest(f) for f in (root / '.git').rglob('*') if f.is_file()}


def fetch(engine, path, data=None):
    import urllib.request
    with urllib.request.urlopen(engine['debug'] + '/debug/' + path, data=data, timeout=30) as response:
        return response.read()


for size in args.sizes:
    fixture = ROOT / ('fixture-' + str(size))
    fixture.mkdir(exist_ok=True)
    if not (fixture / '.git').exists():
        subprocess.run(['git', 'init', '--quiet', str(fixture)], check=True)
    module = fixture / '.dagger/modules/fixture'
    module.mkdir(parents=True, exist_ok=True)
    (module / 'dagger-module.toml').write_text('name = "fixture"\nengineVersion = "v0.21.9"\n[runtime]\nsource = "dang"\n')
    (module / 'dagger.json').unlink(missing_ok=True)
    (fixture / 'dagger.toml').write_text('[modules.fixture]\nsource = ".dagger/modules/fixture"\n')
    payload = fixture / 'payload'
    if not payload.exists() or payload.stat().st_size != size:
        with payload.open('wb') as stream:
            block = bytes(range(256)) * 4096
            remaining = size
            while remaining:
                part = block[:remaining]
                stream.write(part)
                remaining -= len(part)
    payload_hash = digest(payload)
    original_git = metadata(fixture)
    # Two priming pairs, deliberately recorded but excluded from medians.
    rounds = range(1) if args.profile else range(-2, args.pairs)
    for pair in rounds:
        for arm in (['main', 'cli', 'engine'] if pair % 2 == 0 else ['engine', 'cli', 'main']):
            output = fixture / 'out'
            if output.exists():
                shutil.rmtree(output)
            output.mkdir(mode=0o700)
            for name, text, mode in [('old', 'removed', 0o644), ('text', 'original', 0o644),
                                     ('untouched', 'unchanged', 0o664), ('mode-only', 'same', 0o644)]:
                path = output / name
                path.write_text(text)
                path.chmod(mode)
            nonce = str(time.time_ns())
            source = '''# Edit NONCE
type Fixture {
  pub generate(workdir: Directory! @defaultPath(path: "/")): Changeset! @generate {
    workdir
      .withoutFile("out/old")
      .withFile("out/app", workdir.file("payload"), permissions: 488)
      .withNewFile("out/text", "updated NONCE", permissions: 384)
      .withNewFile("out/mode-only", "same", permissions: 384)
      .withNewDirectory("out/empty", permissions: 448)
      .changes(workdir)
  }
}
'''.replace('NONCE', nonce)
            if args.private_source:
                source = source.replace('    workdir\n', '''    let private = directory
      .withNewFile("text", "updated NONCE", permissions: 384)
      .withNewFile("mode-only", "same", permissions: 384)
    workdir
'''.replace('NONCE', nonce), 1)
                source = source.replace('.withNewFile("out/text", "updated ' + nonce + '", permissions: 384)', '.withFile("out/text", private.file("text"))')
                source = source.replace('.withNewFile("out/mode-only", "same", permissions: 384)', '.withFile("out/mode-only", private.file("mode-only"))')
            (module / 'main.dang').write_text(source)
            engine = engines[arm]
            env = dict(os.environ, RUST_CACHE_BENCH_CLI=engine['cli_path'],
                       RUST_CACHE_BENCH_RUNNER=engine['runner'])
            command = ['python3', '/tmp/rust-cache-sipsma-review/local_cli_collector.py', 'generate', '-y']
            label = f'{size}-{pair}-{arm}'
            prefix = logdir / label
            if args.profile:
                assert not json.loads(fetch(engine, 'wcprof/enabled'))['global_enabled']
                try:
                    fetch(engine, 'wcprof/dump')
                except Exception as error:
                    if getattr(error, 'code', None) != 503:
                        raise
                fetch(engine, 'wcprof/enabled', b'on')
            print(json.dumps(dict(event='start', label=label)), flush=True)
            try:
                started = time.monotonic()
                with prefix.with_suffix('.stdout').open('w') as stdout, prefix.with_suffix('.stderr').open('w') as stderr:
                    process = subprocess.Popen(command, cwd=fixture, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
                    def interrupt():
                        try:
                            os.killpg(process.pid, signal.SIGINT)
                        except ProcessLookupError:
                            pass
                    timer = threading.Timer(120, interrupt)
                    timer.daemon = True
                    timer.start()
                    try:
                        # Block on exit. wait(timeout=...) polls in 50 ms
                        # intervals and would quantize small-command timings.
                        process.wait()
                    finally:
                        timer.cancel()
                    result = process
                elapsed = time.monotonic() - started
            finally:
                if args.profile:
                    import gzip
                    fetch(engine, 'wcprof/enabled', b'off')
                    prefix.with_suffix('.wcprof.ndjson.gz').write_bytes(gzip.compress(fetch(engine, 'wcprof/dump'), mtime=0))
            checks = dict(binary_sha256=digest(output / 'app') == payload_hash if (output / 'app').exists() else False,
                          text=(output / 'text').read_text() == 'updated ' + nonce,
                          deletion=not (output / 'old').exists(),
                          untouched=(output / 'untouched').read_text() == 'unchanged',
                          git_metadata=metadata(fixture) == original_git)
            modes = {name: oct((output / name).stat().st_mode & 0o7777) if (output / name).exists() else None
                     for name in ['.', 'app', 'text', 'empty', 'untouched', 'mode-only']}
            row = dict(arm=arm, pair=pair, size=size, warmup=pair < 0, seconds=elapsed,
                       exit_code=result.returncode, cleanup_successful=result.returncode == 0,
                       correct_content=all(checks.values()), checks=checks, modes=modes,
                       fresh_cli=True, source_edit=True, telemetry=True, profiling=args.profile,
                       engine=engine['name'], private_source=args.private_source, source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                       command=command, log=str(prefix))
            samples.append(row)
            (ROOT / (('profile-samples' if args.profile else 'samples') + ('-private-source' if args.private_source else '') + '.json')).write_text(json.dumps(samples, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            assert row['correct_content'] and row['cleanup_successful'], row
            if args.private_source and arm != 'main':
                assert modes == {'.': '0o700', 'app': '0o750', 'text': '0o600', 'empty': '0o700', 'untouched': '0o664', 'mode-only': '0o644'}, modes
    if not args.profile:
        summary = {}
        for tested_size in args.sizes:
            relevant = [r for r in samples if r['size'] == tested_size and not r['warmup']]
            if not relevant:
                continue
            medians = {arm: statistics.median(r['seconds'] for r in relevant if r['arm'] == arm) for arm in engines}
            faster = {arm: sum(next(r['seconds'] for r in relevant if r['pair'] == pair and r['arm'] == arm) <
                                next(r['seconds'] for r in relevant if r['pair'] == pair and r['arm'] == 'main')
                                for pair in range(args.pairs)) for arm in ['cli', 'engine']}
            summary[str(tested_size)] = dict(medians=medians, faster_pairs=faster,
                                            reduction_percent={arm:100*(1-medians[arm]/medians['main']) for arm in ['cli','engine']})
        (ROOT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(dict(event='summary', summary=summary)), flush=True)
