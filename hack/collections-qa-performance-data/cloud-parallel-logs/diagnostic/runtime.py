"""Attribution only: four local primers, one Cloud generation pair and one Cloud artifact pair.

Reuse only the two verified stopped, task-owned old diagnostic containers.
Back up and verify their original binaries before replacement; restore binaries,
fixture bytes and stopped state afterward. Default dry run, no Cloud calls.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

LAB = Path(__file__).resolve().parent
PREVIOUS = Path('/tmp/collections-perf/engine-allocation-round2')
sys.path.insert(0, str(PREVIOUS))
import experiment as x

spec = importlib.util.spec_from_file_location('navigation', PREVIOUS/'navigation-generate.py')
nav = importlib.util.module_from_spec(spec); spec.loader.exec_module(nav)
OUT = LAB/'runtime-v1'
OWNER = 'collections-cloud-transport-v1'
CLI_BUILD = Path('/tmp/collections-perf/cli-exit-tail-v2')
CLI = CLI_BUILD/'dagger-diagnostic'
HEAD = '21939e4ff95dd2be7c584b883b39c5e75b20d703'
VARIANTS = ('baseline', 'parallel')
MIN_FREE, MAX_WRITTEN = 16*1024**3, 8*1024**3
TOP_NUMERIC = {'anchor_unix_ns','snapshot_ns','event_limit','dropped_events',
               'events_total','http_started','http_finished','http_active'}
VALUE_KEYS = {
    'request_content_length','log_class','request_class','records','get_conn_ns',
    'get_conn_attempts','got_conn_ns','got_conn_attempts','connection_acquire_ns',
    'connection_reused','connection_idle','dns_attempts','dns_window_ns','dns_errors',
    'connect_attempts','connect_ns','connect_errors','tls_attempts','tls_window_ns',
    'tls_errors','wrote_request_ns','write_attempts','write_errors','first_byte_ns',
    'response_headers_ns','transport_error','status','response_bytes','response_eof',
    'body_read_errors','body_closed','body_close_error',
}
HTTP_KINDS = {'cloud.traces','cloud.logs','cloud.metrics','cloud.other'}
OLD = Path('/tmp/collections-perf/engine-cloud-transport-audit')
FIELDS = json.loads((OLD/'fixed-labels.json').read_text())
KINDS = set(FIELDS['phase_labels']) | set(FIELDS['http_labels'])


def audit(item):
    # /debug/vars has other fields: parse in memory, retain this object only.
    values = json.loads(x.get(item['port'], '/debug/vars'))['cloud_transport_audit']
    assert set(values) == TOP_NUMERIC | {'events'}
    assert all(isinstance(values[k], int) and not isinstance(values[k], bool) for k in TOP_NUMERIC)
    assert values['dropped_events'] == 0, 'diagnostic buffer saturated'
    assert values['http_started']-values['http_finished'] == values['http_active'] >= 0
    events = values['events'] or []
    last = 0
    for row in events:
        assert set(row) <= {'sequence','kind','start_ns','end_ns','values'}
        assert row['kind'] in KINDS
        assert isinstance(row['sequence'], int) and row['sequence'] > last
        last = row['sequence']
        assert isinstance(row['start_ns'], int) and isinstance(row['end_ns'], int)
        assert 0 <= row['start_ns'] <= row['end_ns'] <= values['snapshot_ns']
        numeric = row.get('values', {})
        assert set(numeric) <= VALUE_KEYS
        assert all(isinstance(v, int) and not isinstance(v, bool) for v in numeric.values())
    assert len(events) == values['events_total'] <= values['event_limit']
    return values


def settle(item, initial):
    # Observed quiet is not proof of Cloud storage/readback or all queues empty.
    start = time.monotonic(); last_change = start; latest = initial
    while time.monotonic()-start < 8:
        if latest['http_active'] == 0 and time.monotonic()-last_change >= .5:
            return latest, time.monotonic()-start, True
        time.sleep(.1)
        following = audit(item)
        assert following['anchor_unix_ns'] == initial['anchor_unix_ns']
        if following['events_total'] != latest['events_total'] or following['http_started'] != latest['http_started']:
            last_change = time.monotonic()
        latest = following
    return latest, time.monotonic()-start, False


def absent(kind, name):
    return subprocess.run(['docker',kind,'inspect',name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--no-profile-workspace', action='store_true')
    parser.add_argument('--cloud-used', type=int, default=202)
    args = parser.parse_args()
    limit = 4
    assert 0 <= args.cloud_used and args.cloud_used+limit <= 220
    if not args.run:
        print(json.dumps({'execute':False,'cloud_commands_max':limit,'local_generation_primers':2,'local_artifact_primers':2,
                          'existing_owned_stopped_engines':2,'new_volumes':0,'cloud_budget_used_before':args.cloud_used,
                          'profile_workspace':not args.no_profile_workspace,'instrumented_attribution_only':True,
                          'binary_replacement':'back up, verify, then restore exact original files while engines are stopped',
                          'output':str(OUT)})); return
    os.umask(0o077)
    assert not OUT.exists(), 'never overwrite or resume a partial trial'
    base = json.loads((PREVIOUS/'prepared.json').read_text())
    state = json.loads((PREVIOUS/'withfile-v1/prepared.json').read_text())
    builds = json.loads((LAB/'build-results.json').read_text())
    for item in builds.values():
        assert item['source_head'] == HEAD and item['instrumented']
        assert x.sha(item['binary']) == item['sha256']
    cli = next(row for row in json.loads((CLI_BUILD/'build-results.json').read_text())['builds'] if row['name']=='diagnostic')
    assert cli['exitCode'] == 0 and x.sha(CLI) == cli['sha256']
    assert all(x.sha(LAB/'manifest.prepared.json') == b['manifest_sha256'] for b in builds.values())
    image = x.capture(['docker','image','inspect','--format','{{.Id}}',base['image']])
    assert image == base['image']
    for path,digest in base['blobs'].items(): assert x.sha(path) == digest
    app, native = PREVIOUS/'greetings', PREVIOUS/'native'
    assert x.fixture_hashes(app) == state['input_sha256']
    native_before = x.fixture_hashes(native); native_expected = dict(native_before)
    originals = {name:(native/name).read_bytes() if (native/name).exists() else None for name in ('input.txt','generated.txt')}
    assert originals['input.txt'] is not None
    expected = {flow:nav.normalize((PREVIOUS/'navigation-generate-v1'/('local-correctness-0-'+flow)/'stdout.txt').read_bytes())
                for flow in ('workspace-files','artifacts')}
    original_engines=json.loads((OLD/'runtime-v1/engines.json').read_text())
    original_builds={'baseline':json.loads((OLD/'baseline-build-result.json').read_text()),
                     'common':json.loads((OLD/'build-result.json').read_text())}
    x.OWNER=OWNER
    for item in original_engines.values():
        info=x.owned(item)
        assert not info['State']['Running'], 'do not replace a running engine binary'
        assert info['Id']==item['id'], 'immutable task container ID changed'
        mounts=[mount for mount in info['Mounts'] if mount['Destination']=='/var/lib/dagger']
        assert len(mounts)==1 and mounts[0]['Type']=='volume' and mounts[0]['Name']==item['name']
        volume=json.loads(x.capture(['docker','volume','inspect',mounts[0]['Name']]))[0]
        assert volume['Labels']['dagger.perf.owner']==OWNER
    OUT.mkdir(mode=0o700); (OUT/'empty-config').mkdir(mode=0o700)
    (OUT/'driver.py.txt').write_bytes(Path(__file__).read_bytes())
    common_env = {k:os.environ[k] for k in ('PATH','HOME','USER','LOGNAME','TMPDIR') if k in os.environ}
    common_env.update(DO_NOT_TRACK='1', DAGGER_NO_UPDATE_CHECK='1', GIT_TERMINAL_PROMPT='0')
    cloud = dict(common_env, DAGGER_CLOUD_URL='https://api.dagger.cloud')
    for k in ('DAGGER_CLOUD_TOKEN','XDG_CONFIG_HOME'):
        if k in os.environ: cloud[k] = os.environ[k]
    local = dict(common_env, XDG_CONFIG_HOME=str(OUT/'empty-config'))
    x.OWNER = OWNER
    engines, setup, rows, attempts, volumes, backups = {}, {}, [], [], [], {}
    written = 0
    x.write(OUT/'provenance.json', {
        'engine_builds':builds,'cli_sha256':cli['sha256'],'image':image,'driver_sha256':x.sha(__file__),
        'helper_sha256':{name:x.sha(PREVIOUS/name) for name in ('experiment.py','navigation-generate.py','withfile-cloud-warm.py')},
        'cloud_budget_used_before':args.cloud_used,'cloud_commands_max':limit,'approved_cloud_budget':220,
        'local_generation_primers':2,'local_artifact_primers':2,'owner':OWNER,'profile_workspace':not args.no_profile_workspace,
        'cache_boundary':'retained owned volumes; two generation plus two artifact local primers; no cold claim',
        'not_cold':'host image/page caches and provisioned SDK blobs may be warm; startup/setup excluded',
        'scope':'both engine and CLI instrumented; attribution only, never ordinary performance medians',
        'generation':'native Dang generator writes unchanged input bytes; output removed before every invocation; not SDK code generation',
        'collection':'retain only cloud_transport_audit from expvar; raw CLI outputs and optional wcprof private',
        'settling':'after exit, require no active observed HTTP and no new events for 500ms within 8s; not DB delivery proof',
        'bounds':{'minimum_free_bytes':MIN_FREE,'cumulative_engine_written_bytes_stop':MAX_WRITTEN,'cli_timeout_seconds':300},
        'fixture_hashes_before':native_before,'resources_deleted':0,
        'original_engine_ids':{k:v['id'] for k,v in original_engines.items()},
        'original_binary_hashes':{k:v['sha256'] for k,v in original_builds.items()},
    })

    def guard():
        assert shutil.disk_usage(LAB).free > MIN_FREE and written < MAX_WRITTEN
        assert x.fixture_hashes(app) == state['input_sha256']
        assert x.fixture_hashes(native) == native_expected

    def run(variant, flow, phase, index, production=True):
        nonlocal written
        assert sum(a['production'] for a in attempts) < limit if production else sum(not a['production'] for a in attempts) < 4
        guard(); item = engines[variant]; generates = flow == 'generate'
        if generates:
            assert (native/'input.txt').read_bytes() == originals['input.txt']
            (native/'generated.txt').unlink(missing_ok=True); native_expected.pop('generated.txt',None)
        guard()
        dest = OUT/f'{len(attempts):02d}-{phase}-{flow}-{variant}'; dest.mkdir()
        profile = flow == 'workspace-files' and not args.no_profile_workspace
        if profile:
            try: (dest/'prior.wcprof').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
            except x.HTTPError as err:
                if err.code != 503: raise
        args_flow = ['-y','generate'] if generates else nav.FLOWS[flow]
        cmd = [str(CLI),'--engine','container://'+item['name']]+(['--profile'] if profile else [])+args_flow
        env = dict(cloud if production else local, DAGGER_PERF_EXIT_TIMELINE=str(dest/'timeline.jsonl'))
        attempt = dict(variant=variant,flow=flow,phase=phase,index=index,production=production,profile=profile,command=cmd)
        attempts.append(attempt); x.write(OUT/'attempts.json',attempts)
        before_audit = audit(item); before_counters = nav.warm.snapshot(item)
        x.write(dest/'engine-before.json',before_audit)
        done, observed = threading.Event(), {}; visible=None; polls=0
        with (dest/'stdout.txt').open('wb') as out, (dest/'stderr.txt').open('wb') as err:
            start, wall = time.monotonic(), time.time_ns()
            proc = subprocess.Popen(cmd,cwd=native if generates else app,env=env,stdout=out,stderr=err,start_new_session=True)
            def waiter():
                observed['exit_code']=proc.wait(); observed['monotonic']=time.monotonic(); observed['unix_ns']=time.time_ns(); done.set()
            worker=threading.Thread(target=waiter,daemon=True); worker.start()
            try:
                if generates:
                    while not done.is_set() and time.monotonic()-start < 300:
                        polls+=1
                        try:
                            if (native/'generated.txt').read_bytes() == originals['input.txt']:
                                visible=time.monotonic(); break
                        except FileNotFoundError: pass
                        done.wait(.005)
                timed_out=not done.wait(max(0,300-(time.monotonic()-start)))
            finally:
                if not done.is_set():
                    try: proc.send_signal(signal.SIGINT)
                    except ProcessLookupError: pass
                    if not done.wait(10):
                        try: os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError: pass
                worker.join(timeout=15); assert not worker.is_alive(), 'owned CLI did not exit'
        if visible is not None and visible > observed['monotonic']: visible=None
        immediate = audit(item); after_counters=nav.warm.snapshot(item)
        x.write(dest/'engine-post-exit-sample.json',immediate)
        settled, wait_seconds, quiet = settle(item,immediate)
        x.write(dest/'engine-settled.json',settled)
        delta=nav.warm.delta(before_counters,after_counters); written+=delta['engine_written_bytes']
        stdout=(dest/'stdout.txt').read_bytes(); stderr=(dest/'stderr.txt').read_bytes()
        correct=not timed_out and observed['exit_code']==0 and quiet
        if generates:
            generated=(native/'generated.txt').read_bytes() if (native/'generated.txt').exists() else None
            correct &= generated==originals['input.txt']
            if generated is not None: native_expected['generated.txt']=hashlib.sha256(generated).hexdigest()
        else: correct &= nav.known_listing(flow,stdout) and nav.normalize(stdout)==expected[flow]
        timeline=[json.loads(line) for line in (dest/'timeline.jsonl').read_text().splitlines()]
        correct &= bool(timeline) and any(event['kind']=='cli.command' for event in timeline)
        correct &= timeline[-1].get('values',{}).get('dropped_events')==0
        new_events=[event for event in settled['events'] if event['sequence'] > before_audit['events_total']]
        uploads=[event for event in new_events if event['kind'] in HTTP_KINDS]
        cli_uploads=[event for event in timeline if event['kind'] in HTTP_KINDS]
        if production:
            correct &= bool(uploads) and bool(cli_uploads)
            correct &= all(200 <= event.get('values',{}).get('status',0) < 300 for event in uploads+cli_uploads)
        else: correct &= not uploads and not cli_uploads
        row=dict(attempt,correct=bool(correct),seconds=observed['monotonic']-start,
                 started_unix_ns=wall,exited_unix_ns=observed['unix_ns'],exit_code=observed['exit_code'],timed_out=timed_out,
                 file_visible_seconds=visible-start if visible is not None else None,
                 file_visibility_censored_at_exit=bool(generates and visible is None and correct),file_poll_count=polls,
                 stdout_sha256=x.sha(dest/'stdout.txt'),stderr_bytes=len(stderr),
                 cloud_link_visible=bool(re.search(rb'https://[^\s]*dagger.cloud/',stdout+stderr)),
                 additional_observed_settle_seconds=wait_seconds,settled_quiet=quiet,
                 engine_http_requests=len(uploads),cli_http_requests=len(cli_uploads),
                 engine_event_first_sequence=before_audit['events_total']+1,engine_event_last_sequence=settled['events_total'],
                 before=before_counters,after=after_counters,**delta)
        rows.append(row); attempt['correct']=bool(correct)
        x.write(OUT/'results.json',rows); x.write(OUT/'attempts.json',attempts)
        if profile: (dest/'run.wcprof').write_bytes(x.get(item['port'],'/debug/wcprof/dump?flush=true'))
        print(json.dumps({k:row[k] for k in ('variant','flow','phase','index','production','seconds','correct','engine_http_requests')}),flush=True)
        assert correct, 'diagnostic validation failed; retained private evidence'
        guard()

    try:
        (OUT/'original-binaries').mkdir(mode=0o700)
        for variant in VARIANTS:
            guard()
            original_key='baseline' if variant=='baseline' else 'common'
            item=dict(original_engines[original_key],sha256=builds[variant]['sha256'])
            assert not x.owned(item)['State']['Running']
            backup=OUT/'original-binaries'/variant
            x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(backup)])
            assert x.sha(backup)==original_builds[original_key]['sha256'], 'original binary changed'
            backups[variant]={'path':str(backup),'sha256':x.sha(backup)}
            engines[variant]=item
            x.write(OUT/'engines.json',engines);x.write(OUT/'backups.json',backups)
            started=time.monotonic()
            x.capture(['docker','cp',builds[variant]['binary'],item['name']+':/usr/local/bin/dagger-engine'])
            setup[variant]={'binary_replace_seconds_excluded':time.monotonic()-started,'startup_seconds_excluded':x.start(item)}
            x.write(OUT/'setup.json',setup)
        for flow in ('generate','artifacts'):
            for variant in VARIANTS:run(variant,flow,'local-primer',0,production=False)
        for index,flow in enumerate(('generate','artifacts')):
            for variant in VARIANTS if index%2==0 else VARIANTS[::-1]:run(variant,flow,'warm',0)
    finally:
        for name, contents in originals.items():
            path=native/name
            if contents is None: path.unlink(missing_ok=True)
            elif not path.exists() or path.read_bytes()!=contents: path.write_bytes(contents)
        stopped=0
        restored_binaries={}
        for variant,item in engines.items():
            if x.owned(item)['State']['Running']:x.capture(['docker','stop','--timeout','30',item['name']])
            stopped+=1
            original=backups[variant]
            assert x.sha(original['path'])==original['sha256']
            x.capture(['docker','cp',original['path'],item['name']+':/usr/local/bin/dagger-engine'])
            verified=OUT/'original-binaries'/(variant+'-restored-check')
            x.capture(['docker','cp',item['name']+':/usr/local/bin/dagger-engine',str(verified)])
            restored_binaries[variant]=x.sha(verified)==original['sha256']
            assert restored_binaries[variant] and not x.owned(item)['State']['Running']

        unchanged=x.fixture_hashes(native)==native_before and x.fixture_hashes(app)==state['input_sha256']
        x.write(OUT/'restoration.json',{'fixtures_restored':unchanged,'owned_engines_stopped':stopped,
                                     'volumes_retained':2,'resources_deleted':0,'original_binaries_restored':restored_binaries,
                                     'cloud_attempts':sum(a['production'] for a in attempts),
                                     'local_attempts':sum(not a['production'] for a in attempts),
                                     'validated_commands':sum(row['correct'] for row in rows),'written_bytes':written})
        assert unchanged
    assert len(rows)==limit+4 and all(row['correct'] for row in rows)
    x.write(OUT/'summary.json',{'complete':True,'attribution_only':True,'cloud_commands':limit,
                              'local_primers':4,'normal_timing_claim':False})


if __name__ == '__main__': main()
