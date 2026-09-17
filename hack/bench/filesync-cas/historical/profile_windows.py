"""Validate foreground CLI intervals and explicitly owned admission tails.

Only the pinned candidate's three admission classes may extend past CLI exit.
No events are removed. Both the full native dump and maintained replay still
have to pass their independent integrity gates.
"""
import json
import subprocess
import time

BACKGROUND = 'filesync.filecache.background'
HANDOFF = 'filesync.filecache.handoff'
BACKGROUND_CLASSES = {BACKGROUND, 'filesync.filecache.remountAndPublish', 'filesync.filecache.publish'}
MAX_TAIL_NS = 10_000_000_000


def decode(text):
    header, *events = [json.loads(line) for line in text.splitlines() if line.strip()]
    return header, events


def finished(header, events):
    strings = header['strings']
    ops = [e for e in events if e['e'] == 'op']
    successful = sum(strings[e['c']] == HANDOFF and e.get('o') == 'ok' for e in ops)
    backgrounds = sum(strings[e['c']] == BACKGROUND for e in ops)
    return not header.get('open_ops') and successful == backgrounds


def validate(record, header, events):
    strings, epoch = header['strings'], header['epoch_unix_nano']
    ops = {e['id']: e for e in events if e['e'] == 'op'}
    roots = {ident for ident, e in ops.items() if strings[e['c']] == BACKGROUND}
    descendants = set(roots)
    while True:
        expanded = descendants | {ident for ident, e in ops.items() if e.get('p') in descendants}
        if expanded == descendants:
            break
        descendants = expanded
    query = [e for e in ops.values() if strings[e['c']] == 'session.serveQuery']
    begin, end = record['started_ns'], record['process_ended_ns']
    gates = {
        'query_complete_and_successful': bool(query) and all(e['o'] == 'ok' for e in query),
        'background_roots_independent': all(not ops[ident].get('p') for ident in roots),
        'only_known_background_classes': all(strings[ops[ident]['c']] in BACKGROUND_CLASSES for ident in descendants),
        'successful_handoffs_completed': finished(header, events),
        'foreground_inside_process_window': True,
        'background_inside_bounded_capture_window': True,
    }
    for event in events:
        ident = event['id'] if event['e'] == 'op' else event.get('p')
        start, stop = epoch + event['s'], epoch + event['d']
        if ident in descendants:
            gates['background_inside_bounded_capture_window'] &= begin <= start <= stop <= min(
                header['dumped_unix_nano'], end + MAX_TAIL_NS)
        else:
            gates['foreground_inside_process_window'] &= begin <= start <= stop <= end
    end_query = max((epoch + e['d'] for e in query), default=end)
    end_background = max((epoch + ops[ident]['d'] for ident in roots), default=end_query)
    stats = {
        'background_roots': len(roots),
        'background_elapsed_ms': sum(ops[ident]['d'] - ops[ident]['s'] for ident in roots) / 1e6,
        'remaining_after_query_ms': max(0, end_background - end_query) / 1e6,
        'remaining_after_cli_ms': max(0, end_background - end) / 1e6,
        'background_outcomes': [ops[ident]['o'] for ident in sorted(roots)],
        'handoff_outcomes': [e['o'] for e in ops.values() if strings[e['c']] == HANDOFF],
    }
    return gates, stats


def capture(directory, container, env, cli_end_ns):
    """Peek without flushing until admission ends, then preserve one full dump."""
    deadline = cli_end_ns + MAX_TAIL_NS
    peeks = []
    while True:
        filename = directory / f'drain-{len(peeks):03d}.wcprof'
        with filename.open('xb') as output:
            subprocess.run(['docker', 'exec', container, '/tmp/cas-debug-get', '/debug/wcprof/dump?flush=0'],
                           env=env, stdout=output, stderr=subprocess.PIPE, check=True, timeout=30)
        header, events = decode(filename.read_text())
        peeks.append({'path': filename.name, 'event_count': header['event_count'],
                      'open_ops': len(header.get('open_ops', [])), 'observed_ns': time.time_ns()})
        assert header['dropped_events'] == 0, 'dropped events during admission capture'
        if finished(header, events):
            break
        assert time.time_ns() < deadline, 'admission did not finish within capture bound; evidence retained'
        time.sleep(.05)
    with (directory / 'profile.wcprof').open('xb') as output:
        subprocess.run(['docker', 'exec', container, '/tmp/cas-debug-get', '/debug/wcprof/dump'],
                       env=env, stdout=output, stderr=subprocess.PIPE, check=True, timeout=30)
    return {'peeks': peeks, 'bound_after_cli_ms': MAX_TAIL_NS / 1e6,
            'cli_timer_extended': False, 'events_filtered': False,
            'note': 'Diagnostic dump/drain happens after CLI timing and before the next validation-separated import.'}
