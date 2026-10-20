"""Check complete real-repository output; this first run is not a timing cohort."""
from pathlib import Path
import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time

out = Path('/tmp/go-listing-current-main-oct20')
sys.path.insert(0, '/tmp/go-collection-upstream-review-oct19')
from config_dagql_benchmark_helpers import cpu, engine_info, heap, pressure

parser = argparse.ArgumentParser()
parser.add_argument('--variant', choices=['main', 'candidate'], required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--timeout', type=int, default=600)
args = parser.parse_args()
info = json.loads((out / 'engine.json').read_text())
engine = engine_info(info['name'], info['runner'], info['debug'])
root = Path('/tmp/dagger-go-collection-current-main')
config, source, test = root / 'dagger.toml', root / 'dagql/types.go', root / 'dagql/cache_test.go'
original = {p: p.read_bytes() for p in [config, source, test]}
module = out / 'go-sorted-inputs'
module_files = [module / 'go.dang', module / 'gomod/main.dang']
candidate = {p: p.read_bytes() for p in module_files}
if args.variant == 'main':
    for file in module_files:
        file.write_bytes((out / 'go-main' / file.relative_to(module)).read_bytes())
expected = {tuple(row) for row in json.loads(Path('/tmp/go-collection-upstream-review-oct19/root-test-inventory.json').read_text())['rows']}
marker = 'TestOrderedPathListing' + str(time.time_ns())
expected.add(('dagql', marker))
assert len(expected) == 4483
directory = out / 'full-listing'
directory.mkdir(exist_ok=True)
prefix = directory / args.label
assert not prefix.with_suffix('.result.json').exists()
cli = out / 'main-cli'
env = dict(os.environ, GOMAXPROCS='8', RUST_CACHE_BENCH_RUNNER=engine['runner'],
           RUST_CACHE_BENCH_CLI=str(cli),
           RUST_CACHE_BENCH_COLLECTOR='http://' + Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip() + ':43184',
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(cli), _EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.20')
command = ['python3', '/tmp/rust-cache-sipsma-review/local_cli_collector.py',
           'check', '--module', 'go', '--check', 'test', '--list', '--all']
rows, row_times = [], []
process = None
try:
    config.write_text('[modules.go]\nsource = "' + str(module) + '"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
    source.write_bytes(original[source] + ('\n// Full listing verification ' + marker + '\n').encode())
    test.write_bytes(original[test] + ('\nfunc ' + marker + '(t *testing.T) {}\n').encode())
    before_heap, before_cpu, before_pressure = heap(engine), cpu(engine), pressure()
    tick = time.monotonic()
    with prefix.with_suffix('.stdout').open('w') as stdout, prefix.with_suffix('.stderr').open('w') as stderr:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE,
                                   stderr=stderr, text=True, start_new_session=True)
        state = dict(driver_pid=os.getpid(), helper_pid=process.pid, label=args.label,
                     variant=args.variant, state='running', command=command)
        (out / 'full-listing-process.json').write_text(json.dumps(state, indent=2)+'\n')
        def read_stdout():
            for line in process.stdout:
                stdout.write(line)
                stdout.flush()
                fields = line.split()
                if fields and fields[0] == 'go':
                    rows.append(tuple(fields[1:3]))
                    row_times.append(time.monotonic()-tick)
        reader = threading.Thread(target=read_stdout)
        reader.start()
        timed_out = False
        while process.poll() is None:
            if time.monotonic()-tick >= args.timeout:
                timed_out = True
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=15)
                break
            try:
                process.wait(timeout=min(15, max(.1, args.timeout-(time.monotonic()-tick))))
            except subprocess.TimeoutExpired:
                print(json.dumps(dict(event='running', label=args.label,
                                      seconds=round(time.monotonic()-tick,1), rows=len(rows))), flush=True)
        elapsed = time.monotonic()-tick
        reader.join(timeout=10)
    after_heap = heap(engine)
    result = dict(variant=args.variant, label=args.label, purpose='complete-output correctness smoke; not a benchmark cohort',
                  seconds=elapsed, exit_code=process.returncode, timed_out=timed_out,
                  rows=len(rows), expected_rows=len(expected), correct_names=set(rows)==expected,
                  correct_order=rows==sorted(expected), first_row_seconds=row_times[0] if row_times else None,
                  last_row_seconds=row_times[-1] if row_times else None, profiling=False, telemetry=True,
                  fresh_cli=True, source_edit=True, test_edit=True, cleanup_successful=process.returncode==0 and not timed_out,
                  engine_cpu=cpu(engine)-before_cpu, allocated_bytes=after_heap['TotalAlloc']-before_heap['TotalAlloc'],
                  gc_cycles=after_heap['NumGC']-before_heap['NumGC'],
                  cpu_pressure_fraction=(pressure()-before_pressure)/(elapsed*1e6))
    prefix.with_suffix('.result.json').write_text(json.dumps(result, indent=2)+'\n')
    state.update(state='finished', exit_code=process.returncode)
    (out / 'full-listing-process.json').write_text(json.dumps(state, indent=2)+'\n')
    print(json.dumps(result), flush=True)
finally:
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=45)
    for file, data in original.items():
        file.write_bytes(data)
    for file, data in candidate.items():
        file.write_bytes(data)
