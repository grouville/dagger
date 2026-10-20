"""Locate the slow phase; this interrupted, profiled run is not a benchmark."""
from pathlib import Path
import gzip
import json
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from config_dagql_benchmark_helpers import cpu, engine_info, heap

out = Path('/tmp/go-collection-upstream-review-oct19')
directory = out / 'full-listing-gap-profile'
directory.mkdir(exist_ok=False)
info = json.loads((out / 'config-dagql-engines.json').read_text())['main']
engine = engine_info(info['name'], info['runner'], info['debug'])
root = Path('/tmp/dagger-go-collection-current-main')
source, test = root / 'dagql/types.go', root / 'dagql/cache_test.go'
original_source, original_test = source.read_bytes(), test.read_bytes()
assert b'source = "/tmp/go-collection-clean-go-main"' in (root / 'dagger.toml').read_bytes()
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
port = sock.getsockname()[1]
sock.close()
cli = out / 'config-dagql-cli'
env = dict(os.environ, GOMAXPROCS='8', RUST_CACHE_BENCH_RUNNER=engine['runner'],
           RUST_CACHE_BENCH_CLI=str(cli),
           RUST_CACHE_BENCH_COLLECTOR='http://' + Path('/tmp/rust-cache-sipsma-review/otlp-null-address.txt').read_text().strip() + ':43184',
           _EXPERIMENTAL_DAGGER_CLI_BIN=str(cli), _EXPERIMENTAL_DAGGER_VERSION='v1.0.0-beta.20',
           PPROF='127.0.0.1:' + str(port))
command = ['python3', '/tmp/rust-cache-sipsma-review/local_cli_collector.py',
           'check', '--module', 'go', '--check', 'test', '--list', '--all']
stop = threading.Event()
threads, errors, captures, rows = [], [], [], []
process = None

def fetch(url, target=None, data=None, timeout=30):
    with urllib.request.urlopen(url, data=data, timeout=timeout) as response:
        value = response.read()
    if target is not None:
        (directory / target).write_bytes(value)
    return value

def dump(name):
    try:
        data = fetch(engine['debug'] + '/debug/wcprof/dump', timeout=60)
    except urllib.error.HTTPError as error:
        if name == 'prior-buffer' and error.code == 503:
            return
        raise
    (directory / (name + '.ndjson.gz')).write_bytes(gzip.compress(data, mtime=0))

def capture_process(label, debug):
    for offset in [10, 40, 70]:
        if stop.wait(max(0, tick + offset - time.monotonic())):
            break
        start = time.monotonic()-tick
        try:
            fetch(debug + '/debug/pprof/goroutine?debug=2', label + '-goroutines-' + str(offset) + '.txt')
            fetch(debug + '/debug/pprof/profile?seconds=10', label + '-cpu-' + str(offset) + '.pprof', timeout=20)
            captures.append(dict(process=label, start=start, end=time.monotonic()-tick))
        except Exception as error:
            errors.append(dict(process=label, offset=offset, error=str(error)))

dump('prior-buffer')
before_heap, before_cpu = heap(engine), cpu(engine)
fetch(engine['debug'] + '/debug/pprof/allocs', 'engine-allocs-before.pprof')
marker = 'TestListingGap' + str(time.time_ns())
source.write_bytes(original_source + ('\n// Profile listing gap ' + marker + '\n').encode())
test.write_bytes(original_test + ('\nfunc ' + marker + '(t *testing.T) {}\n').encode())
fetch(engine['debug'] + '/debug/wcprof/enabled', data=b'on')
tick = time.monotonic()
try:
    with (directory / 'stdout').open('w') as stdout, (directory / 'stderr').open('w') as stderr:
        process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=stderr,
                                   text=True, start_new_session=True)
        def read_stdout():
            for line in process.stdout:
                stdout.write(line)
                stdout.flush()
                if line.startswith('go '):
                    rows.append(line.rstrip())
        reader = threading.Thread(target=read_stdout)
        reader.start()
        for label, debug in [('engine', engine['debug']), ('cli', 'http://127.0.0.1:' + str(port))]:
            thread = threading.Thread(target=capture_process, args=(label, debug))
            threads.append(thread)
            thread.start()
        interrupted = False
        while process.poll() is None:
            if time.monotonic()-tick >= 90:
                interrupted = True
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=15)
                break
            try:
                process.wait(timeout=min(15, max(.1, 90-(time.monotonic()-tick))))
            except subprocess.TimeoutExpired:
                current = heap(engine)
                print(json.dumps(dict(event='profiling', seconds=round(time.monotonic()-tick, 1),
                                      rows=len(rows), engine_cpu=cpu(engine)-before_cpu,
                                      allocated_bytes=current['TotalAlloc']-before_heap['TotalAlloc'])), flush=True)
        elapsed = time.monotonic()-tick
        reader.join(timeout=10)
finally:
    stop.set()
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=45)
    for thread in threads:
        thread.join(timeout=25)
    fetch(engine['debug'] + '/debug/wcprof/enabled', data=b'off')
    source.write_bytes(original_source)
    test.write_bytes(original_test)
dump('capture')
fetch(engine['debug'] + '/debug/pprof/allocs', 'engine-allocs-after.pprof')
after_heap = heap(engine)
report = dict(engine=info, source=str(root), command=command, profiling=True,
              excluded_from_benchmarks=True, seconds=elapsed, rows=len(rows), interrupted=interrupted,
              exit_code=process.returncode, captures=captures, errors=errors,
              engine_cpu=cpu(engine)-before_cpu,
              allocated_bytes=after_heap['TotalAlloc']-before_heap['TotalAlloc'],
              allocations=after_heap['Mallocs']-before_heap['Mallocs'],
              gc_cycles=after_heap['NumGC']-before_heap['NumGC'])
(directory / 'result.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report), flush=True)
