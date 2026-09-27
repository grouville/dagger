"""Prepared LOCAL-only Address/d685 lifecycle; importing it does not run commands.

The composing, reviewed driver owns its fixtures and exact command cap. This helper
owns one temporary engine only; it never starts/modifies/deletes the original engine
or its retained volume. No experimental init/transport or Cloud configuration.
"""
from pathlib import Path
import hashlib, importlib.util, json, os, re, resource, shutil, signal, socket
import subprocess, sys, threading, time, uuid

HERE = Path(__file__).resolve().parent
LAB = Path('/tmp/collections-perf/engine-allocation-round2')
sys.path.insert(0, str(LAB))
import experiment as x
spec = importlib.util.spec_from_file_location('sdk36_navigation', LAB / 'navigation-generate.py')
nav = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nav)
ORIGINAL_OWNER = 'collections-lazy-core-runtime-v1'
OWNER = 'collections-dang-registration-v1'
ORIGINAL = '56f2eaccf6bf2f3151fb4c08205e1ad33fa7730ad5dee32577e867b527fc4b12'
IMAGE = 'sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
CLI = Path('/tmp/collections-perf/shared-client-transport-v1/prototype-v2/builds/dagger-original')
CLI_SHA = 'd68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8'


INPUTS_SHA = '63d64e849586874a275223fc36346ad208c198d98d88dd20db599fc0338fa06a'
MIN_FREE = 16 * 1024**3
MAX_WRITE = 8 * 1024**3
ANSI = re.compile(rb'\x1b\[[0-9;]*[A-Za-z]')


class EngineLifecycle:
    def __init__(self, output_dir, max_calls, variant):
        assert variant in ('baseline', 'candidate')
        self.variant = variant
        self.out = Path(output_dir)
        assert self.out.parent.resolve() == HERE.resolve() and not self.out.exists()
        assert isinstance(max_calls, int) and 1 <= max_calls <= 9
        self.max_calls = max_calls
        self.item = self.original = self.volume = None
        self.planned = None
        self.init_sha = None
        self.rows, self.attempts = [], []
        self.written = 0
        self.cli = CLI
        self.expected_version = None
        self.engine_sha = None
        self.closed = False

    def __enter__(self):
        os.umask(0o077)
        self.out.mkdir()
        (self.out / 'empty-config').mkdir()
        self.env = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
        self.env.update(XDG_CONFIG_HOME=str(self.out / 'empty-config'), DO_NOT_TRACK='1',
            DAGGER_NO_UPDATE_CHECK='1', GIT_TERMINAL_PROMPT='0')
        try:
            self._start()
        except BaseException:
            self.close()
            raise
        return self

    def _start(self):
        freeze = json.loads((HERE / 'frozen-runtime-inputs.json').read_text())
        assert x.sha(HERE / ('frozen-' + self.variant + '-engine-manifest.json')) == freeze['engine_manifest_sha256'][self.variant]
        manifest = json.loads((HERE / ('frozen-' + self.variant + '-engine-manifest.json')).read_text())
        assert manifest['source_head'] == freeze['source_head']
        assert manifest['scope'] == freeze['engine_scope']
        engine = manifest['engine']
        assert engine['exit_code'] == 0 and x.sha(engine['path']) == engine['sha256']
        self.engine_sha = engine['sha256']
        self.expected_version = manifest['expected_core_version'].encode()
        assert x.sha(manifest['recipe_path']) == manifest['recipe_sha256']
        assert x.sha(CLI) == CLI_SHA
        assert x.sha(HERE / 'frozen-sdk-inputs.json') == INPUTS_SHA
        inputs = json.loads((HERE / 'frozen-sdk-inputs.json').read_text())
        assert inputs['cli_sha256'] == CLI_SHA
        for path, want in inputs['sdk_blobs'].items():
            assert x.sha(path) == want
        self.original = json.loads((LAB / 'lazy-core-runtime-v1/engines.json').read_text())['lazy']
        assert self.original['sha256'] == ORIGINAL
        x.OWNER = ORIGINAL_OWNER
        info = x.owned(self.original)
        assert not info['State']['Running']
        mounts = [m for m in info['Mounts'] if m['Destination'] == '/var/lib/dagger']
        assert len(mounts) == 1 and mounts[0]['Type'] == 'volume' and mounts[0]['Name'] == self.original['name']
        self.volume = json.loads(x.capture(['docker', 'volume', 'inspect', mounts[0]['Name']]))[0]
        assert self.volume['Labels']['dagger.perf.owner'] == ORIGINAL_OWNER
        self.guard()
        image = json.loads(x.capture(['docker', 'image', 'inspect', IMAGE]))[0]
        assert image['Id'] == IMAGE
        for assignment in image['Config'].get('Env') or []:
            key = assignment.partition('=')[0]
            assert not any(token in key.upper() for token in ('CLOUD', 'TOKEN', 'SECRET', 'OTEL_EXPORTER', 'REMOTE_CACHE'))
        for kind in ('engine', 'init'):
            path = self.out / ('original-' + kind + '-before.private')
            x.capture(['docker', 'cp', self.original['name'] + ':/usr/local/bin/dagger-' + kind, str(path)])
            if kind == 'engine':
                assert x.sha(path) == ORIGINAL
            else:
                self.init_sha = x.sha(path)
        run_id = uuid.uuid4().hex
        name = 'dagger-engine.collections-dang-registration-' + run_id[:12]
        assert not x.capture(['docker', 'ps', '-aq', '--filter', 'name=^/' + name + '$'])
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        self.planned = {'name': name, 'run_id': run_id, 'port': port}
        x.write(self.out / 'planned-engine.private.json', self.planned)
        cid = subprocess.check_output(['docker', 'create', '--name', name, '--label', 'dagger.perf.owner=' + OWNER,
            '--label', 'dagger.perf.run=' + run_id,
            '--privileged', '-p', f'127.0.0.1:{port}:6060', '-v', self.volume['Name'] + ':/var/lib/dagger',
            '-e', 'DAGGER_TYPESCRIPT_SDK_MANIFEST_DIGEST=sha256:2a8f755cfe5322aeeee861f646c58d6b796a585d2794db47b5b71ba14f6f3fef',
            '-e', '_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT=', IMAGE, '--debugaddr=0.0.0.0:6060'], text=True, timeout=60).strip()
        self.item = {'name': name, 'id': cid, 'port': port, 'sha256': self.engine_sha}
        self.selector = 'container+docker://' + name
        x.OWNER = OWNER
        check = x.owned(self.item)
        assert check['Image'] == IMAGE and not check['State']['Running']
        assert check['HostConfig']['PortBindings'] == {'6060/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(port)}]}
        assert any(m['Type'] == 'volume' and m['Name'] == self.volume['Name'] and m['Destination'] == '/var/lib/dagger' for m in check['Mounts'])
        blobs = {Path(path).name: Path(path) for path in inputs['sdk_blobs']}
        assert len(blobs) == len(inputs['sdk_blobs'])
        for filename, path in blobs.items():
            x.capture(['docker', 'cp', str(path), name + ':/usr/local/share/dagger/content/blobs/sha256/' + filename])
        x.capture(['docker', 'cp', engine['path'], name + ':/usr/local/bin/dagger-engine'])
        seconds = x.start(self.item)
        assert x.capture(['docker', 'exec', name, 'sha256sum', '/usr/local/bin/dagger-engine']).split()[0] == self.engine_sha
        installed_init = x.capture(['docker', 'exec', name, 'sha256sum', '/usr/local/bin/dagger-init']).split()[0]
        assert installed_init == self.init_sha, 'ordinary image init differs from retained original'
        x.write(self.out / 'lifecycle-provenance.private.json', {
            'owner': OWNER, 'engine': self.item, 'original': self.original,
            'cli_sha256': CLI_SHA, 'manifest_sha256': freeze['engine_manifest_sha256'][self.variant],
            'sdk_inputs_sha256': x.sha(HERE / 'frozen-sdk-inputs.json'),
            'lifecycle_sha256': x.sha(__file__), 'original_init_sha256': self.init_sha,
            'expected_core_version': self.expected_version.decode(), 'startup_seconds_excluded': seconds,
            'max_local_calls': self.max_calls, 'cloud_commands': 0,
            'write_counter_scope': 'CLI-bracketing engine writes only; excludes engine startup and gaps.'})
        self.guard()

    def guard(self):
        assert shutil.disk_usage(HERE).free > MIN_FREE and self.written < MAX_WRITE
        if self.original is None:
            return
        live = x.inspect(self.original['name'])
        assert live['Id'] == self.original['id'] and live['Config']['Labels']['dagger.perf.owner'] == ORIGINAL_OWNER
        assert not live['State']['Running'], 'original engine started during experiment'
        if self.volume is None:
            return
        users = x.capture(['docker', 'ps', '--no-trunc', '-q', '--filter', 'volume=' + self.volume['Name']]).splitlines()
        if self.item is not None and x.owned(self.item)['State']['Running']:
            assert users == [self.item['id']], 'retained volume has another active user'
        else:
            assert not users, 'retained volume already in use'

    def run(self, args, cwd, validator, label, *, profile=False, timeout=300, output_path=None, expected_bytes=None):
        """Run one bounded CLI call. validator(row, stdout_bytes, stderr_bytes) -> bool."""
        assert callable(validator) and re.fullmatch(r'[a-z0-9-]+', label)
        assert isinstance(args, list) and all(isinstance(arg, str) for arg in args)
        assert 1 <= timeout <= 600 and len(self.attempts) < self.max_calls
        assert not any(arg == '--engine' or arg.startswith('--engine=') for arg in args)
        self.guard()
        dest = self.out / f'{len(self.attempts):02d}-{label}'
        dest.mkdir()
        attempt = {'index': len(self.attempts), 'label': label, 'profile': profile,
            'args': args, 'cwd': str(Path(cwd).resolve())}
        self.attempts.append(attempt)
        x.write(self.out / 'attempts.private.json', self.attempts)
        if profile:
            try:
                (dest / 'prior.wcprof.private').write_bytes(x.get(self.item['port'], '/debug/wcprof/dump?flush=true'))
            except x.HTTPError as err:
                if err.code != 503:
                    raise
        command = [str(CLI), '--engine', self.selector] + (['--profile'] if profile else []) + args
        before, usage = nav.warm.snapshot(self.item), resource.getrusage(resource.RUSAGE_CHILDREN)
        done, observed = threading.Event(), {}
        visible, polls = None, 0
        already_current = output_path is not None and output_path.exists() and output_path.read_bytes() == expected_bytes
        with (dest / 'stdout.private').open('wb') as stdout, (dest / 'stderr.private').open('wb') as stderr:
            begin, started = time.monotonic(), time.time_ns()
            proc = subprocess.Popen(command, cwd=cwd, env=self.env, stdout=stdout, stderr=stderr, start_new_session=True)
            def wait():
                observed.update(code=proc.wait(), end=time.monotonic(), wall=time.time_ns())
                done.set()
            worker = threading.Thread(target=wait, daemon=True)
            worker.start()
            try:
                if output_path is not None and not already_current:
                    while not done.is_set() and time.monotonic() - begin < timeout:
                        polls += 1
                        try:
                            if output_path.read_bytes() == expected_bytes:
                                visible = time.monotonic()
                                break
                        except FileNotFoundError:
                            pass
                        done.wait(.005)
                timed_out = not done.wait(max(0, timeout - (time.monotonic() - begin)))
            finally:
                if not done.is_set():
                    try:
                        proc.send_signal(signal.SIGINT)
                    except ProcessLookupError:
                        pass
                    if not done.wait(10):
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                worker.join(15)
                assert not worker.is_alive()
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        delta = nav.warm.delta(before, nav.warm.snapshot(self.item))
        self.written += delta['engine_written_bytes']
        stdout, stderr = (dest / 'stdout.private').read_bytes(), (dest / 'stderr.private').read_bytes()
        text = ANSI.sub(b'', stdout + b'\n' + stderr)
        links = re.findall(rb'https://[^\s\x1b]*dagger.cloud/[^\s\x1b]*', text)
        unexpected = any(url.rstrip(b'.') != b'https://dagger.cloud/traces/setup' for url in links)
        row = {'index': attempt['index'], 'label': label, 'profile': profile,
            'seconds': observed['end'] - begin, 'started_unix_ns': started,
            'exited_unix_ns': observed['wall'], 'exit_code': observed['code'],
            'timed_out': timed_out, 'unexpected_cloud_link': unexpected,
            'file_visible_seconds': visible-begin if visible is not None else None,
            'file_visibility_poll_interval_ms': 5 if output_path is not None else None,
            'file_visibility_polls': polls, 'output_already_current': already_current,
            'stdout_sha256': x.sha(dest / 'stdout.private'),
            'process_tree_user_seconds': after.ru_utime - usage.ru_utime,
            'process_tree_system_seconds': after.ru_stime - usage.ru_stime, **delta}
        row['correct'] = not timed_out and not unexpected and bool(validator(row, stdout, stderr))
        if profile:
            (dest / 'run.wcprof.private').write_bytes(x.get(self.item['port'], '/debug/wcprof/dump?flush=true'))
            row['profile_sha256'] = x.sha(dest / 'run.wcprof.private')
        self.rows.append(row)
        x.write(self.out / 'results.json', self.rows)
        print(json.dumps({key: row[key] for key in ('index', 'label', 'seconds', 'exit_code', 'correct')}), flush=True)
        assert row['correct'], 'correctness gate failed: ' + label
        self.guard()
        return row, stdout, stderr

    def close(self):
        if self.closed:
            return
        self.closed = True
        errors = []
        facts = {'temporary_container_removed': self.item is None, 'original_engine_stopped': None,
            'original_engine_binary_untouched': None, 'original_init_binary_untouched': None,
            'retained_volume_preserved': None, 'cloud_commands': 0, 'volumes_deleted': 0,
            'local_attempts': len(self.attempts), 'validated_commands': sum(row['correct'] for row in self.rows),
            'engine_written_bytes': self.written}
        if self.item is None and self.planned is not None:
            try:
                # Docker may complete creation after its caller timed out. Recover
                # only this planned unique name with both labels, image and volume.
                matches = x.capture(['docker', 'ps', '-aq', '--no-trunc',
                    '--filter', 'name=^/' + self.planned['name'] + '$',
                    '--filter', 'label=dagger.perf.owner=' + OWNER,
                    '--filter', 'label=dagger.perf.run=' + self.planned['run_id']]).splitlines()
                assert len(matches) <= 1
                if matches:
                    info = x.inspect(matches[0])
                    assert info['Name'] == '/' + self.planned['name'] and info['Image'] == IMAGE
                    assert info['Config']['Labels']['dagger.perf.owner'] == OWNER
                    assert info['Config']['Labels']['dagger.perf.run'] == self.planned['run_id']
                    mounts = [m for m in info['Mounts'] if m['Destination'] == '/var/lib/dagger']
                    assert len(mounts) == 1 and mounts[0]['Type'] == 'volume' and mounts[0]['Name'] == self.volume['Name']
                    self.item = {'name': self.planned['name'], 'id': info['Id'],
                        'port': self.planned['port'], 'sha256': self.engine_sha}
                    facts['temporary_container_removed'] = False
                facts['late_created_container_recovered'] = bool(matches)
            except BaseException as err:
                errors.append(type(err).__name__)
        if self.item is not None:
            try:
                x.OWNER = OWNER
                if x.owned(self.item)['State']['Running']:
                    x.capture(['docker', 'stop', '--timeout', '30', self.item['name']])
                assert not x.owned(self.item)['State']['Running']
                x.capture(['docker', 'rm', self.item['id']])
                facts['temporary_container_removed'] = True
            except BaseException as err:
                errors.append(type(err).__name__)
        try:
            x.OWNER = ORIGINAL_OWNER
            if self.original is not None:
                facts['original_engine_stopped'] = not x.owned(self.original)['State']['Running']
                for kind in ('engine', 'init'):
                    path = self.out / ('original-' + kind + '-after.private')
                    x.capture(['docker', 'cp', self.original['name'] + ':/usr/local/bin/dagger-' + kind, str(path)])
                    expected = ORIGINAL if kind == 'engine' else self.init_sha
                    facts['original_' + kind + '_binary_untouched'] = x.sha(path) == expected if expected is not None else None
            if self.volume is not None:
                current = json.loads(x.capture(['docker', 'volume', 'inspect', self.volume['Name']]))[0]
                facts['retained_volume_preserved'] = all(current[key] == self.volume[key] for key in ('Name', 'CreatedAt', 'Driver', 'Labels'))
        except BaseException as err:
            errors.append(type(err).__name__)
        facts['cleanup_error_types'] = errors
        x.write(self.out / 'lifecycle-restoration.json', facts)
        assert not errors and not any(value is False for key, value in facts.items() if key.endswith(('removed', 'stopped', 'untouched', 'preserved'))), 'engine cleanup or restoration gate failed'

    def __exit__(self, kind, value, traceback):
        self.close()
        return False
