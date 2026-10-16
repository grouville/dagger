from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import signal
import subprocess
import threading
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--execute', action='store_true')
parser.add_argument('--timeout', type=float, default=120)
parser.add_argument('--package')
parser.add_argument('--label', default='official')
parser.add_argument('--workspace',type=Path,default=Path('/home/dagger/dagger_otra'))
parser.add_argument('--go-source', default='/tmp/dagger-go-official-collections-oct16')
args = parser.parse_args()
base = Path('/tmp/rust-cache-sipsma-review')
root = Path(__file__).parent / ('real-go-' + ('execution' if args.execute else 'discovery') + ('-' + args.package.replace('/', '_') if args.package else '') + '-' + args.label)
root.mkdir(exist_ok=False)
debug = 'http://127.0.0.1:16104/debug/'
engine_name = 'dagger-rust-parser-state-pool-oct14'
def get(route, data=None, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(debug + route, data=data), timeout=timeout) as response:
        return json.load(response)
record = json.loads(subprocess.check_output(['docker', 'inspect', engine_name]))[0]
cgroup = Path('/sys/fs/cgroup') / Path(f"/proc/{record['State']['Pid']}/cgroup").read_text().split(':', 2)[2].strip().lstrip('/')
env = dict(os.environ, RUST_CACHE_BENCH_RUNNER='tcp://127.0.0.1:16276', RUST_CACHE_BENCH_CLI=str(base/'dagger-artifact-list-buffered'), RUST_CACHE_BENCH_COLLECTOR='http://'+(base/'otlp-null-address.txt').read_text().strip()+':43184')
command = ['python3', str(base/'local_cli_collector.py'), 'check', '--module', 'go', '--check', 'test']
if not args.execute:
    command += ['--list', '--all']
if args.package:
    command += ['--go-package=' + args.package]
assert not get('client-lifecycle').get('sessions'), 'other engine clients active'
assert not get('layercopy-known-dirs')['enabled']
start_time = datetime.now(timezone.utc).isoformat()
before_events = (cgroup/'memory.events').read_text()
stop = threading.Event()
samples = []
def sample():
    next_dump = 0
    while not stop.wait(.25):
        row = dict(seconds=time.monotonic()-tick)
        for name in ['memory.current', 'memory.peak', 'memory.events', 'cpu.stat', 'io.pressure']:
            try: row[name] = (cgroup/name).read_text().strip()
            except OSError as error: row[name] = str(error)
        if row['seconds'] >= next_dump:
            try:
                row['heap'] = {k: v for k, v in get('vars')['memstats'].items() if k in ['HeapAlloc', 'HeapObjects', 'TotalAlloc', 'NumGC']}
                if row['seconds'] >= 2:
                    with urllib.request.urlopen(debug+'pprof/goroutine?debug=2', timeout=5) as response:
                        (root/f'goroutines-{int(row["seconds"])}.txt').write_bytes(response.read())
            except Exception as error: row['debug_error'] = str(error)
            next_dump = row['seconds'] + 5
        samples.append(row)
        (root/'memory.json').write_text(json.dumps(samples, indent=2)+'\n')
def capture_cpu():
    for label,at,seconds in [('early',0,5),('packages',30,10),('expansion',85,10),('late',150,10),('tail',220,10)]:
        if stop.wait(max(0, at-(time.monotonic()-tick))): break
        begin=time.time()
        try:
            with urllib.request.urlopen(debug+'pprof/profile?seconds='+str(seconds),timeout=seconds+20) as response:
                (root/(label+'.pprof')).write_bytes(response.read())
            (root/(label+'-window.json')).write_text(json.dumps(dict(start=begin,end=time.time(),command_offset=begin-wall_tick))+'\n')
        except Exception as error: (root/(label+'-error.txt')).write_text(str(error))

with urllib.request.urlopen(debug+'pprof/allocs', timeout=30) as response:
    (root/'allocs-before.pprof').write_bytes(response.read())
get('wcprof/enabled', b'on')
with urllib.request.urlopen(debug+'wcprof/dump', timeout=15) as response:
    response.read()
tick = time.monotonic()
wall_tick = time.time()
thread = threading.Thread(target=sample, daemon=True)
thread.start()
cpu_thread=threading.Thread(target=capture_cpu,daemon=True)
cpu_thread.start()
cancelled = False
workspace = args.workspace
source_path = workspace/'dagql/types.go'
source_original = source_path.read_bytes()
(root/'edited-source-before.go.txt').write_bytes(source_original)
originals = {name: (workspace/name).read_bytes() if (workspace/name).exists() else None for name in ['dagger.toml', 'dagger.lock']}
(root/'original-dagger.toml').write_bytes(originals['dagger.toml'])
try:
    source_path.write_bytes(source_original + ('\n// Go listing performance diagnostic '+str(time.time_ns())+'\n').encode())
    (workspace/'dagger.toml').write_text('[modules.go]\nsource = "'+args.go_source+'"\n[modules.go.settings]\nversion = "1.26.6"\ngoflags = "-p=8"\ntest = ["."]\n')
    with (root/'command.log').open('w') as output:
        process = subprocess.Popen(command, cwd=workspace, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try: code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            cancelled = True
            os.killpg(process.pid, signal.SIGINT)
            code = process.wait()
finally:
    source_path.write_bytes(source_original)
    for name, original in originals.items():
        if original is None: (workspace/name).unlink(missing_ok=True)
        else: (workspace/name).write_bytes(original)
elapsed = time.monotonic()-tick
stop.set(); thread.join(timeout=20); cpu_thread.join(timeout=40)
with urllib.request.urlopen(debug+'pprof/allocs', timeout=30) as response:
    (root/'allocs-after.pprof').write_bytes(response.read())
profile_error = None
try:
    get('wcprof/enabled', b'off')
    with urllib.request.urlopen(debug+'wcprof/dump', timeout=30) as response:
        (root/'wcprof.ndjson').write_bytes(response.read())
except Exception as error: profile_error = str(error)
state = json.loads(subprocess.check_output(['docker', 'inspect', engine_name]))[0]['State']
with (root/'engine.log').open('w') as output:
    try:
        subprocess.run(['docker', 'logs', '--since', start_time, engine_name], stdout=output, stderr=subprocess.STDOUT, timeout=10)
    except subprocess.TimeoutExpired:
        (root/'log-reader-timeout.json').write_text(json.dumps({'scope':'docker logs reader only','timeout_seconds':10})+'\n')
result = dict(command=command, seconds=elapsed, exit_code=code, cancelled=cancelled, engine_state={k:state[k] for k in ['Status','Running','OOMKilled','ExitCode','Error']}, memory_events_before=before_events, memory_events_after=(cgroup/'memory.events').read_text() if cgroup.exists() else None, profile_error=profile_error, official_go_revision='334136faaa1cd36ac26dfdc648eda907ce99c063', go_source=args.go_source, workspace=str(workspace),workspace_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=workspace,text=True).strip(), go_source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.go_source,text=True).strip(), engine_sha256=subprocess.check_output(['docker','exec',engine_name,'sha256sum','/usr/local/bin/dagger-engine'],text=True).split()[0], interface_field_snapshots=get('interface-field-snapshots')['enabled'])
(root/'result.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2), flush=True)
