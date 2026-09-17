"""Independent revalidation of captured async-aware samples, without filtering."""
from collections import Counter
import json
import re

import build
import profile_windows
from summarize_filesync_pairs import describe, pruning_log, union_ns


def load(directory, spec, helpers):
    record = json.loads((directory / 'receipt.json').read_text())
    assert record['status'] == 'source-and-async-profile-validated-diagnostic-only', record.get('error')
    assert record['exit_code'] == record['analyzer_exit_code'] == 0
    assert record['controller_sha256'] == helpers['profile_async.py']
    assert record['window_helper_sha256'] == helpers['profile_windows.py']
    assert record['image']['id'] == spec['image'] and record['image']['cli_sha256'] == spec['cli_sha256']
    assert record['image']['source_pins'] == spec['source_pins']
    assert all(record['native_analyzer_gates'].values())
    assert build.sha(directory / 'source-manifest.json') == record['source_manifest_sha256']
    assert build.sha(directory / 'profile.wcprof') == record['profile_sha256']
    header, events = profile_windows.decode((directory / 'profile.wcprof').read_text())
    assert header['schema_version'] == 1 and header['event_count'] == len(events)
    assert header['dropped_events'] == 0 and not header.get('open_ops')
    gates, tail = profile_windows.validate(record, header, events)
    assert all(gates.values()) and tail == record['admission_tail']
    analysis = (directory / 'analysis.txt').read_text()
    counts = re.search(r'ops:\s*(\d+)\s+roots:\s*(\d+)\s+open at dump:\s*(\d+)\s+dropped events:\s*(\d+)', analysis)
    drift = re.search(r'simulated baseline makespan:.*?\(drift vs actual:\s*([+-]?[\d.]+)%\)', analysis)
    ops = [e for e in events if e['e'] == 'op']
    assert counts and int(counts[1]) == len(ops) and counts[3] == counts[4] == '0'
    assert drift and abs(float(drift[1])) <= 2
    strings = header['strings']
    classes = {}
    for event in ops:
        classes.setdefault(strings[event['c']], []).append(event)
    durations = {name: union_ns([(e['s'], e['d']) for e in values]) / 1e6 for name, values in classes.items()}
    data = json.loads((directory / 'stdout').read_text())['host']['directory']
    source = json.loads((directory / 'source-manifest.json').read_text())
    import hashlib
    assert data['digest'] == record['content_digest']
    assert hashlib.sha256(data['file']['contents'].encode()).hexdigest() == record['probe_sha256']
    assert source['crates/ruff/src/lib.rs']['sha256'] == record['probe_sha256']
    walks = []
    for line in (directory / 'stderr').read_text().splitlines():
        start = line.find('{"kind":"filesync.client.walk"')
        if start >= 0:
            walk, _ = json.JSONDecoder().raw_decode(line[start:])
            fields = ('enumerate_filter_ns', 'entry_info_ns', 'packet_bookkeeping_ns', 'stat_send_ns')
            assert not walk['failed'] and all(walk[key] >= 0 for key in fields)
            assert sum(walk[key] for key in fields) == walk['walk_ns']
            walks.append(walk)
    assert walks == record['phase_diagnostics']['client_walks'] and max(w['entries'] for w in walks) >= 12025
    assert record['milliseconds'] >= durations['session.serveQuery']
    assert record['admission_capture']['events_filtered'] is False
    assert record['admission_capture']['cli_timer_extended'] is False
    return {
        'receipt': str(directory / 'receipt.json'), 'receipt_sha256': build.sha(directory / 'receipt.json'),
        'profile_sha256': record['profile_sha256'], 'analysis_sha256': build.sha(directory / 'analysis.txt'),
        'engine_ms': durations['session.serveQuery'], 'cli_ms': record['milliseconds'],
        'class_ms': durations, 'class_counts': dict(Counter(strings[e['c']] for e in ops)),
        'admission': tail, 'client_walks': walks, 'content_digest': record['content_digest'],
        'started_ns': record['started_ns'], 'process_ended_ns': record['process_ended_ns'],
        'pressure_before': record['pressure_before'], 'pressure_after': record['pressure_after'],
        'owner': record['owner'], 'source_manifest_sha256': record['source_manifest_sha256'],
    }, source
