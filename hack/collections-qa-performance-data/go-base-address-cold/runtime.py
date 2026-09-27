#!/usr/bin/env python3
"""Four LOCAL first-listing calls, ABBA, each on a new owned Dagger volume.

No primer, preparatory build/pull, Cloud, profile, or existing engine/volume mutation.
The host image, packaged SDK blobs and host page cache remain available.
Default cleanup removes only our containers; fresh volumes stay stopped for
inspection. --cleanup-volumes is an explicit separate, ownership-checked step.
"""
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
import argparse, hashlib, json, os, re, resource, shutil, signal
import subprocess, threading, time, uuid

HERE = Path(__file__).resolve().parent
LAB = Path('/tmp/collections-perf')
APP = LAB / 'engine-allocation-round2/greetings'
GATE = LAB / 'go-base-address-retained-v1'
IMAGE = 'sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
SDK = 'sha256:2a8f755cfe5322aeeee861f646c58d6b796a585d2794db47b5b71ba14f6f3fef'
OWNER = 'collections-go-base-address-cold-v1'
LABEL = 'dagger.perf.owner'
RUN_LABEL = 'dagger.perf.run'
MIN_FREE, MAX_WRITE, CAP = 16 * 1024**3, 8 * 1024**3, 4
ORDER = ('control', 'candidate', 'candidate', 'control')
HTTP = build_opener(ProxyHandler({}))
ANSI = re.compile(rb'\x1b\[[0-9;]*[A-Za-z]')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def capture(args, timeout=45):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


def inspect(kind, name):
    return json.loads(capture(['docker', kind, 'inspect', name]))[0]


def exists(kind, name):
    return subprocess.run(['docker', kind, 'inspect', name], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=30).returncode == 0


def owned(item):
    info = inspect('container', item['id'])
    assert info['Id'] == item['id'] and info['Name'] == '/' + item['name']
    assert info['Config']['Labels'].get(LABEL) == OWNER and info['Image'] == IMAGE
    assert info['Config']['Labels'].get(RUN_LABEL) == item['run_id']
    mounts = [m for m in info['Mounts'] if m['Destination'] == '/var/lib/dagger']
    assert len(mounts) == 1 and mounts[0]['Type'] == 'volume' and mounts[0]['Name'] == item['name']
    return info


def volume_owned(item):
    volume = inspect('volume', item['name'])
    assert volume['Labels'].get(LABEL) == OWNER
    assert volume['Labels'].get(RUN_LABEL) == item['run_id']
    assert item['volume_created_at'] is not None
    assert volume['CreatedAt'] == item['volume_created_at']
    return volume


def group_for(item):
    pid = owned(item)['State']['Pid']
    assert pid > 0
    relative = Path('/proc', str(pid), 'cgroup').read_text().split('::')[1].strip().lstrip('/')
    group = Path('/sys/fs/cgroup') / relative
    return group.parent if group.name == 'init' else group


def io_totals(group):
    result = {}
    for line in (group / 'io.stat').read_text().splitlines():
        for key, value in (part.split('=') for part in line.split()[1:]):
            result[key] = result.get(key, 0) + int(value)
    return result


def snapshot(group):
    disks = {}
    for line in Path('/proc/diskstats').read_text().splitlines():
        fields = line.split()
        if re.fullmatch(r'(nvme[0-9]+n[0-9]+|sd[a-z]+|vd[a-z]+)', fields[2]):
            disks[fields[2]] = list(map(int, fields[3:]))
    return {
        'host_diskstats': disks,
        'engine_io': io_totals(group),
        'engine_cpu': {line.split()[0]: int(line.split()[1]) for line in (group / 'cpu.stat').read_text().splitlines()},
        'host_psi_us': {kind: {line.split()[0]: int(line.rsplit('=', 1)[1]) for line in Path('/proc/pressure', kind).read_text().splitlines()} for kind in ('cpu', 'io', 'memory')},
        'free_disk_bytes': shutil.disk_usage(HERE).free,
        'host_dirty_writeback_kib': {line.split()[0].rstrip(':'): int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith(('Dirty:', 'Writeback:'))},
    }


def delta(before, after):
    result = {'host_diskstats_delta': {name: [b-a for a, b in zip(values, after['host_diskstats'][name])] for name, values in before['host_diskstats'].items() if name in after['host_diskstats']}}
    for kind in ('engine_io', 'engine_cpu'):
        result[kind] = {key: after[kind].get(key, 0)-before[kind].get(key, 0) for key in set(before[kind]) | set(after[kind])}
    result['host_psi_us'] = {kind: {key: after['host_psi_us'][kind][key]-value for key, value in values.items()} for kind, values in before['host_psi_us'].items()}
    for key in ('free_disk_bytes', 'host_dirty_writeback_kib'):
        result[key + '_before'] = before[key]
        result[key + '_after'] = after[key]
    return result


def hashes(root):
    result = {}
    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name not in ('.git', 'node_modules')]
        for name in files:
            path = Path(directory) / name
            assert path.is_file() and not path.is_symlink(), 'unexpected fixture entry'
            result[str(path.relative_to(root))] = sha(path)
    return result


def cleanup_volumes():
    out = HERE / 'results-v1'
    state = json.loads((out / 'cleanup.json').read_text())
    assert state['fixture_restored'] and state['original_fixture_untouched']
    items = json.loads((out / 'resources.json').read_text())
    assert len(items) <= CAP
    removed = []
    for item in items:
        assert not exists('container', item['name'])
        if item['volume_created_at'] is None:
            assert not exists('volume', item['name'])
            continue
        assert not capture(['docker', 'ps', '-aq', '--filter', 'volume=' + item['name']])
        volume_owned(item)
        capture(['docker', 'volume', 'rm', item['name']])
        assert not exists('volume', item['name'])
        removed.append(item['name'])
    write(out / 'volume-cleanup.json', {'removed_owned_volumes': removed, 'existing_resources_modified': False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--cleanup-volumes', action='store_true')
    args = parser.parse_args()
    if args.cleanup_volumes:
        cleanup_volumes()
        return
    if not args.run:
        print(json.dumps({'execute': False, 'cli_cap': CAP, 'cloud_calls': 0, 'order': ORDER, 'new_volumes': 4, 'primers': 0, 'profiles': 0, 'minimum_free_bytes': MIN_FREE, 'sampled_write_guard_bytes': MAX_WRITE, 'default_cleanup': 'stop/remove only new containers; preserve four owned volumes for separate explicit cleanup'}))
        return
    os.umask(0o077)
    frozen = json.loads((HERE / 'frozen-inputs.json').read_text())
    for path, wanted in frozen['source_sha256'].items():
        assert sha(path) == wanted, 'frozen input changed: ' + path
    gate = json.loads((GATE / 'summary-v5.json').read_text())
    assert gate['validated_cli_commands'] == 9 and gate['original_greetings_untouched'] and gate['synthetic_restored']
    manifest = json.loads(Path(frozen['engine_manifest']).read_text())
    assert manifest['engine']['sha256'] == '38711bd2b42e410f9fbf601d4260b47718e8169f7ff1d2caa29313adfba4569c'
    assert manifest['baseline_ancestry_engine_sha256'] == 'ec6a2d88ca54b1c12fc81c7381538e23d100fece04d703daac0b17dcf3d3ebc1'
    assert sha(manifest['engine']['path']) == manifest['engine']['sha256']
    assert sha(manifest['cli']['path']) == manifest['cli']['sha256']
    assert sha(manifest['recipe_path']) == manifest['recipe_sha256']
    image = inspect('image', IMAGE)
    assert image['Id'] == IMAGE
    forbidden = ('DAGGER_CLOUD', 'OTEL_', '_EXPERIMENTAL_DAGGER_CACHE', 'AWS_', 'GOOGLE_APPLICATION_CREDENTIALS')
    assert not any(entry.partition('=')[0].startswith(forbidden) for entry in image['Config'].get('Env', []))
    sdk_inputs = json.loads((GATE / 'frozen-sdk-inputs.json').read_text())
    blobs = {Path(path).name: Path(path) for path in sdk_inputs['sdk_blobs']}
    assert len(blobs) == len(sdk_inputs['sdk_blobs'])
    for path, wanted in sdk_inputs['sdk_blobs'].items():
        assert sha(path) == wanted
    original = json.loads(Path(frozen['fixture_inventory']).read_text())['input_sha256']
    assert hashes(APP) == original
    out = HERE / 'results-v1'
    workspace = HERE / 'greetings-v1'
    assert not out.exists() and not workspace.exists()
    assert shutil.disk_usage(HERE).free > MIN_FREE
    out.mkdir(); (out / 'empty-config').mkdir(mode=0o700)
    for name in original:
        destination = workspace / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(APP / name, destination)
    subprocess.run(['git', 'init', '-q', str(workspace)], check=True, timeout=10)
    subprocess.run(['git', '-C', str(workspace), 'add', '-f', '.'], check=True, timeout=10)
    initial_config = (workspace / 'dagger.toml').read_bytes()
    initial_lock = (workspace / 'dagger.lock').read_bytes()
    local = workspace / '.dagger/perf-go'
    local.mkdir(parents=True)
    (local / 'dagger-module.toml').write_bytes(Path(frozen['module_manifest']).read_bytes())
    assert initial_config.count(b'source = "github.com/dagger/go@collections"') == 1
    control_config = initial_config.replace(b'source = "github.com/dagger/go@collections"', b'source = ".dagger/perf-go"')
    needle = b'base = "dag://backend/go-test-base"'
    assert control_config.count(needle) == 1
    configs = {'control': control_config, 'candidate': control_config.replace(needle, b'baseAddress = "dag://backend/go-test-base"')}
    modules = {variant: Path(frozen[variant + '_module']) for variant in ('control', 'candidate')}
    wanted_rows = [b' '.join(line.split()) for line in Path(frozen['listing_golden']).read_bytes().splitlines() if line.strip()]
    assert len(wanted_rows) == 14
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR') if key in os.environ}
    env.update(XDG_CONFIG_HOME=str(out / 'empty-config'), DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1', GIT_TERMINAL_PROMPT='0')
    assert not any(key.startswith(('DAGGER_CLOUD', 'OTEL_')) for key in env)
    nonce = uuid.uuid4().hex[:12]
    items, attempts, rows = [], [], []
    cumulative_writes = 0
    write(out / 'provenance.json', {
        'frozen_inputs_sha256': sha(HERE / 'frozen-inputs.json'), 'source_sha256': sha(__file__),
        'image': IMAGE, 'sdk_manifest': SDK, 'engine': manifest['engine'], 'cli': manifest['cli'],
        'engine_version': manifest['expected_core_version'], 'same_workspace_path': True,
        'module_sha256': {variant: sha(path) for variant, path in modules.items()},
        'order': ORDER, 'local_cli_cap': CAP, 'cloud_commands': 0,
        'cache_boundary': 'Four newly created, never-started Dagger volumes. Host image/SDK blobs/pages and external registry/Git/CDN caches are retained. No host cache flush or preparatory image pull. Fetches/builds performed by the first Dagger command remain inside its measured wall time. Existing engine/volume untouched.',
        'timing_boundary': 'Full CLI Popen through blocking process wait; provisioning, engine start/readiness, fixture changes, counters and cleanup excluded and recorded separately.',
        'scope': 'Two correlated observations per arm in one ABBA block; not a general cold distribution. Same frozen SDK/engine stack, module base versus optional baseAddress only.',
        'diagnostic_limits': 'No phase profile is collected. Wall/CPU/disk counters alone cannot prove compiler attribution.',
        'bounds': {'min_free_bytes': MIN_FREE, 'sampled_cumulative_engine_write_bytes': MAX_WRITE, 'cli_timeout_seconds': 300, 'sampling_seconds': .5, 'write_scope': 'Engine lifetime before each final stop, not final stop writeback or Docker provisioning.'},
        'cleanup_policy': 'Stop/remove only this run\'s labeled immutable container IDs. Keep its four owned volumes after success/failure; explicit --cleanup-volumes requires evidence, matching labels/creation time, and zero attached containers. No reused volume is referenced.'})
    def guard():
        assert shutil.disk_usage(HERE).free > MIN_FREE and cumulative_writes < MAX_WRITE
        assert hashes(APP) == original
    try:
        # Provision all four containers while stopped, before any sample.
        for index, variant in enumerate(ORDER):
            guard(); start = time.monotonic()
            name = f'dagger-engine.collections-address-cold-{nonce}-{index}'
            assert not exists('container', name) and not exists('volume', name)
            item = {'index': index, 'variant': variant, 'name': name, 'id': None,
                    'run_id': nonce, 'volume_created_at': None}
            items.append(item); write(out / 'resources.json', items)
            capture(['docker', 'volume', 'create', '--label', LABEL + '=' + OWNER,
                     '--label', RUN_LABEL + '=' + nonce, name])
            volume = inspect('volume', name)
            assert volume['Labels'].get(LABEL) == OWNER and volume['Labels'].get(RUN_LABEL) == nonce
            item['volume_created_at'] = volume['CreatedAt']
            write(out / 'resources.json', items)
            item['id'] = capture(['docker', 'create', '--name', name, '--label', LABEL + '=' + OWNER, '--label', RUN_LABEL + '=' + nonce, '--privileged', '-p', '127.0.0.1::6060', '-v', name + ':/var/lib/dagger', '-e', 'DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST=' + SDK, '-e', '_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT=', IMAGE, '--debugaddr=0.0.0.0:6060'])
            write(out / 'resources.json', items)
            assert owned(item)['State']['Status'] == 'created'; volume_owned(item)
            capture(['docker', 'cp', manifest['engine']['path'], item['id'] + ':/usr/local/bin/dagger-engine'])
            for filename, path in blobs.items():
                capture(['docker', 'cp', str(path), item['id'] + ':/usr/local/share/dagger/content/blobs/sha256/' + filename])
            item['provisioning_seconds_excluded'] = time.monotonic() - start
            write(out / 'resources.json', items)
        for item in items:
            guard(); variant = item['variant']
            (workspace / 'dagger.toml').write_bytes(configs[variant])
            (workspace / 'dagger.lock').write_bytes(initial_lock)
            (local / 'go.dang').write_bytes(modules[variant].read_bytes())
            expected_fixture = hashes(workspace)
            assert owned(item)['State']['Status'] == 'created'
            begin_start = time.monotonic(); capture(['docker', 'start', item['id']])
            info = owned(item); port = int(info['NetworkSettings']['Ports']['6060/tcp'][0]['HostPort'])
            deadline = time.monotonic() + 45
            while True:
                try:
                    with HTTP.open(f'http://127.0.0.1:{port}/debug/pprof/', timeout=1): pass
                    break
                except OSError:
                    assert time.monotonic() < deadline, 'engine readiness timeout'
                    time.sleep(.1)
            item['start_to_debug_ready_seconds_excluded'] = time.monotonic() - begin_start
            # This shell checksum is setup, not a Dagger client/session or primer.
            assert capture(['docker', 'exec', item['id'], 'sha256sum', '/usr/local/bin/dagger-engine']).split()[0] == manifest['engine']['sha256']
            write(out / 'resources.json', items)
            group = group_for(item); before = snapshot(group)
            assert cumulative_writes + before['engine_io'].get('wbytes', 0) < MAX_WRITE
            assert len(attempts) < CAP
            dest = out / f'{item["index"]}-{variant}'; dest.mkdir()
            attempts.append({'index': item['index'], 'variant': variant}); write(out / 'attempts.json', attempts)
            command = [manifest['cli']['path'], '--engine', 'container+docker://' + item['name'], 'check', '-l', '--all']
            done = threading.Event(); observed = {}; reason = None
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            with (dest / 'stdout.private').open('wb') as stdout, (dest / 'stderr.private').open('wb') as stderr:
                begin = time.monotonic(); wall = time.time_ns()
                proc = subprocess.Popen(command, cwd=workspace, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
                def waiter():
                    observed.update(code=proc.wait(), end=time.monotonic(), wall=time.time_ns()); done.set()
                thread = threading.Thread(target=waiter, daemon=True); thread.start()
                try:
                    while not done.wait(.5):
                        if time.monotonic() - begin > 300: reason = 'command timeout'; break
                        if shutil.disk_usage(HERE).free <= MIN_FREE: reason = 'free disk floor'; break
                        if cumulative_writes + io_totals(group).get('wbytes', 0) >= MAX_WRITE: reason = 'engine write guard'; break
                finally:
                    if not done.is_set():
                        try: proc.send_signal(signal.SIGINT)
                        except ProcessLookupError: pass
                        if not done.wait(10):
                            try: os.killpg(proc.pid, signal.SIGKILL)
                            except ProcessLookupError: pass
                    thread.join(15); assert not thread.is_alive()
            after = snapshot(group); cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
            raw = (dest / 'stdout.private').read_bytes(); stderr = (dest / 'stderr.private').read_bytes()
            normalized = [b' '.join(line.split()) for line in ANSI.sub(b'', raw).splitlines() if line.strip()]
            urls = re.findall(rb'https://[^\s\x1b]*dagger.cloud/[^\s\x1b]*', raw + b'\n' + stderr)
            cloud = any(url.rstrip(b'.') != b'https://dagger.cloud/traces/setup' for url in urls)
            correct = reason is None and observed['code'] == 0 and normalized == wanted_rows and not cloud
            row = {'index': item['index'], 'variant': variant, 'phase': 'first-cli-new-volume', 'seconds': observed['end'] - begin, 'started_unix_ns': wall, 'exited_unix_ns': observed['wall'], 'exit_code': observed['code'], 'guard_abort': reason, 'correct': correct, 'stdout_rows': len(normalized), 'stdout_sha256': sha(dest / 'stdout.private'), 'unexpected_cloud_link': cloud, 'process_tree_user_seconds': cpu.ru_utime-usage.ru_utime, 'process_tree_system_seconds': cpu.ru_stime-usage.ru_stime, 'provisioning_seconds_excluded': item['provisioning_seconds_excluded'], 'start_to_debug_ready_seconds_excluded': item['start_to_debug_ready_seconds_excluded'], 'module_sha256': sha(local / 'go.dang'), 'config_sha256': sha(workspace / 'dagger.toml'), 'initial_lock_sha256': hashlib.sha256(initial_lock).hexdigest(), 'ordinary_lock_after_sha256': sha(workspace / 'dagger.lock'), **delta(before, after)}
            rows.append(row); write(out / 'results.json', rows)
            print(json.dumps({key: row[key] for key in ('index', 'variant', 'seconds', 'correct', 'engine_io')}), flush=True)
            actual = hashes(workspace)
            assert {k:v for k,v in actual.items() if k != 'dagger.lock'} == {k:v for k,v in expected_fixture.items() if k != 'dagger.lock'}
            assert correct, 'first-listing gate failed; output remains private'
            final = snapshot(group); cumulative_writes += final['engine_io'].get('wbytes', 0)
            item['accounted_engine_written_bytes'] = final['engine_io'].get('wbytes', 0)
            write(out / f'{item["index"]}-before-stop-counters.json', final)
            assert cumulative_writes < MAX_WRITE; guard()
            stop_start = time.monotonic(); capture(['docker', 'stop', '--timeout', '30', item['id']], timeout=45)
            assert not owned(item)['State']['Running']
            item['stop_seconds_excluded'] = time.monotonic()-stop_start
            write(out / 'resources.json', items)
    finally:
        cleanup = []
        for item in items:
            record = {'index': item['index'], 'container_removed': False,
                      'volume_created': False, 'volume_retained': False}
            try:
                # A Docker CLI may fail after the daemon created the resource.
                # Recover only this unique planned name with both ownership labels.
                if item['volume_created_at'] is None and exists('volume', item['name']):
                    volume = inspect('volume', item['name'])
                    assert volume['Labels'].get(LABEL) == OWNER
                    assert volume['Labels'].get(RUN_LABEL) == item['run_id']
                    item['volume_created_at'] = volume['CreatedAt']
                if item['id'] is None and exists('container', item['name']):
                    info = inspect('container', item['name'])
                    assert info['Config']['Labels'].get(LABEL) == OWNER
                    assert info['Config']['Labels'].get(RUN_LABEL) == item['run_id']
                    item['id'] = info['Id']
                    owned(item)  # Includes exact image and volume-attachment checks.
                if item['id']:
                    if owned(item)['State']['Running']:
                        # A failed command still contributes its startup/CLI writes.
                        # This remains a pre-stop sample, not final writeback.
                        final = snapshot(group_for(item))
                        written = final['engine_io'].get('wbytes', 0)
                        cumulative_writes += written - item.get('accounted_engine_written_bytes', 0)
                        item['accounted_engine_written_bytes'] = written
                        write(out / f'{item["index"]}-cleanup-before-stop-counters.json', final)
                        capture(['docker', 'stop', '--timeout', '30', item['id']], timeout=45)
                    capture(['docker', 'rm', item['id']])
                record['container_removed'] = not exists('container', item['name'])
                if item['volume_created_at'] is not None:
                    volume_owned(item)
                    record['volume_created'] = record['volume_retained'] = True
                else:
                    assert not exists('volume', item['name'])
            except Exception as error:
                record['cleanup_error_type'] = type(error).__name__
            cleanup.append(record)
        write(out / 'resources.json', items)
        (workspace / 'dagger.toml').write_bytes(initial_config)
        (workspace / 'dagger.lock').write_bytes(initial_lock)
        if local.exists(): shutil.rmtree(local)
        restoration = {'created_resources': cleanup, 'fixture_restored': hashes(workspace) == original, 'original_fixture_untouched': hashes(APP) == original, 'attempts': len(attempts), 'validated_commands': sum(row['correct'] for row in rows), 'cloud_commands': 0, 'engine_written_bytes_before_final_stops': cumulative_writes, 'volumes_deliberately_retained': sum(row['volume_retained'] for row in cleanup), 'timing_claim': 'four individual first-listing observations; no hidden primer and no compiler attribution'}
        write(out / 'cleanup.json', restoration)
        assert restoration['fixture_restored'] and restoration['original_fixture_untouched']
        assert all(row['container_removed'] and row['volume_created'] == row['volume_retained'] and 'cleanup_error_type' not in row for row in cleanup)
    assert len(rows) == CAP and all(row['correct'] for row in rows)


if __name__ == '__main__':
    main()
