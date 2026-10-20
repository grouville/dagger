"""Compare complete real-repository listings with only cache backing changed."""
from pathlib import Path
import argparse
import json
import os
import signal
import subprocess
import threading
import time

from config_dagql_benchmark_helpers import cpu, engine_info, heap, pressure

parser = argparse.ArgumentParser()
parser.add_argument('--arm', choices=['main', 'dagql', 'lru'], required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--timeout', type=int, default=180)
args = parser.parse_args()
out = Path('/tmp/go-collection-upstream-review-oct19')
records = json.loads((out / 'config-dagql-engines.json').read_text())
info = (json.loads((out / 'config-comparison-lru-engine.json').read_text())
        if args.arm == 'lru' else records['candidate' if args.arm == 'dagql' else 'main'])
engine = engine_info(info['name'], info['runner'], info['debug'])
root = Path('/tmp/dagger-go-collection-current-main')
config = root / 'dagger.toml'
assert b'source = "/tmp/go-collection-clean-go-main"' in config.read_bytes()
assert b'test = ["."]' in config.read_bytes()
source = root / 'dagql/types.go'
test = root / 'dagql/cache_test.go'
original_source, original_test = source.read_bytes(), test.read_bytes()
inventory = json.loads((out / 'root-test-inventory.json').read_text())
expected = {tuple(row) for row in inventory['rows']}
assert len(expected) == 4482
marker = 'TestCollectionCache' + str(time.time_ns())
expected.add(('dagql', marker))
source.write_bytes(original_source + ('\n// Listing cache comparison ' + marker + '\n').encode())
test.write_bytes(original_test + ('\nfunc ' + marker + '(t *testing.T) {}\n').encode())
logdir = out / 'config-cache-full-listing'
logdir.mkdir(exist_ok=True)
prefix = logdir / args.label
assert not prefix.with_suffix('.result.json').exists()
cli = out / 'config-dagql-cli'
env = dict(os.environ, GOMAXPROCS='8', RUST_CACHE_BENCH_RUNNER=engine['runner'],
           RUST_CACHE_BENCH_CLI=str(cli),
           RUST_CACHE_BENCH_COLLECTOR='http://' + Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip() + ':43184',
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(cli), _EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.20')
for key in ['PPROF', 'CPUPROFILE']:
    env.pop(key, None)
command = ['python3', '/tmp/rust-cache-sipsma-review/local_cli_collector.py',
           'check', '--module', 'go', '--check', 'test', '--list', '--all']
rows, row_times, memory = [], [], []
stop = threading.Event()
process = None
try:
    deadline, quiet = time.monotonic() + 90, 0
    while quiet < 2:
        before, stall, start = cpu(engine), pressure(), time.monotonic()
        time.sleep(1)
        elapsed = time.monotonic() - start
        admitted = (cpu(engine)-before)/elapsed < .15 and (pressure()-stall)/(elapsed*1e6) < .10
        quiet = quiet+1 if admitted else 0
        assert time.monotonic() < deadline, 'engine/host did not become quiet'
    before_heap, before_cpu, before_pressure = heap(engine), cpu(engine), pressure()
    memory_file = Path(engine['cgroup']) / 'memory.current'
    memory.append(int(memory_file.read_text()))
    def sample_memory():
        while not stop.wait(.25):
            memory.append(int(memory_file.read_text()))
    sampler = threading.Thread(target=sample_memory)
    sampler.start()
    tick = time.monotonic()
    timed_out = False
    with prefix.with_suffix('.stdout').open('w') as stdout, prefix.with_suffix('.stderr').open('w') as stderr:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE,
                                   stderr=stderr, text=True, start_new_session=True)
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
        while process.poll() is None:
            if time.monotonic()-tick > args.timeout:
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
                print(json.dumps(dict(event='running', arm=args.arm, label=args.label,
                                      seconds=round(time.monotonic()-tick, 1), rows=len(rows))), flush=True)
        elapsed = time.monotonic()-tick
        reader.join(timeout=10)
    stop.set()
    sampler.join()
    after_heap = heap(engine)
    report = dict(arm=args.arm, label=args.label, engine=info['name'], base=info['base'],
                  binary_sha256=info['binary_sha256'], seconds=elapsed,
                  exit_code=process.returncode, timed_out=timed_out,
                  rows=len(rows), expected_rows=len(expected), correct_names=set(rows)==expected,
                  correct_order=rows==sorted(expected), unique_test_name=marker,
                  first_row_seconds=row_times[0] if row_times else None,
                  last_row_seconds=row_times[-1] if row_times else None,
                  engine_cpu=cpu(engine)-before_cpu,
                  allocated_bytes=after_heap['TotalAlloc']-before_heap['TotalAlloc'],
                  allocations=after_heap['Mallocs']-before_heap['Mallocs'],
                  gc_cycles=after_heap['NumGC']-before_heap['NumGC'],
                  memory_before=memory[0], peak_memory_current=max(memory), memory_after=int(memory_file.read_text()),
                  cpu_pressure_fraction=(pressure()-before_pressure)/(elapsed*1e6),
                  fresh_cli=True, source_edit=True, test_edit=True, telemetry=True,
                  cleanup_successful=process.returncode==0 and not timed_out,
                  profile=False, cache_policy_overrides=False)
    prefix.with_suffix('.result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)
finally:
    stop.set()
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=45)
    source.write_bytes(original_source)
    test.write_bytes(original_test)
