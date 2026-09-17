#!/usr/bin/env python3
"""Render a detailed companion from the fully validated, frozen matrix result.

Does not run experiments, modify raw evidence, or change the frozen analyzer.
Nested operation times and sender work counters remain separate from elapsed
query/CLI timing. Existing outputs are never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent
ARMS = ('main', 'both', 'async')
FLOWS = {
    'initial': 'Cold import',
    'exact': 'Unchanged after cold',
    'leaf1': 'One-file edit',
    'leaf1-exact': 'Repeat one-file edit',
    'leaf2': 'Move populated directory into a subdirectory',
    'ab1-exact': 'Repeat directory move',
    'revert': 'Restore directory',
    'ab2-edit': 'Mixed: 128 edits, 64 additions, 64 deletions',
    'ab2-exact': 'Repeat mixed diff',
    'ab3-edit': 'Restore mixed diff',
    'ab4-edit': 'Broad directory/file reorganization, additions and deletions',
    'ab4-exact': 'Repeat broad reorganization',
    'ab5-edit': 'Restore broad reorganization',
}
DETAIL_FLOWS = ('initial', 'exact', 'leaf1', 'leaf2', 'ab2-edit', 'ab4-edit')
PHASES = (
    ('filesync.phase.sync', 'Source sync, comparison and hash updates'),
    ('filesync.phase.checksum', 'Tree checksum'),
    ('filesync.phase.copy', 'Materialize new result (inclusive)'),
    ('filesync.filecache.lookup', '  CAS lookup (inside materialization)'),
    ('filesync.filecache.ingest', '  New CAS file writes (inside materialization)'),
    ('filesync.phase.commit', 'Commit result snapshot'),
    ('filesync.phase.publish', 'Publish result metadata (inclusive)'),
    ('filesync.filecache.handoff', '  Async ownership handoff (inside publication)'),
    ('filesync.phase.release', 'Release import resources'),
)


def render(report, source_sha, contention_note=None):
    assert report['status'] == 'complete-validated-n6'
    assert report['completed_rounds'] == list(range(1, 7)) and not report['issues']
    samples = report['samples']
    index = {(s['round'], s['arm'], s['flow']): s for s in samples}
    assert len(samples) == len(index) == 234
    assert set(index) == {(r, a, f) for r in range(1, 7) for a in ARMS for f in FLOWS}

    def values(arm, flow, extract):
        return [extract(index[r, arm, flow]) for r in range(1, 7)]

    def typical(arm, flow, extract):
        return median(values(arm, flow, extract))

    lines = [
        '# Detailed Ruff filesync comparison', '',
        f'Validated input SHA-256: `{source_sha}`.', '',
        'Six matched rounds, 234 profiled CLI commands, three versions. All times are milliseconds.', '',
        'Main is pinned upstream 523f3fe3 plus common diagnostics and the same reserve-floor GC fix.',
        'Both CAS versions also include the xattr opt-out and result-first writer. Only the async version',
        'adds detached admission. This compares filesync, not Cargo or the Rust module.', '',
        'Cold means a fresh engine volume and CLI state. Engine images and host OS page caches were available;',
        'it is not a complete first installation or a cold-disk test.', '',
    ]
    if contention_note:
        lines += ['## Host contention: diagnostic series', '',
                  'External Rust/C compilation was observed during round 5. The user canceled it and a subsequent',
                  'process check found no remaining compiler processes. The exact contention onset is not known.',
                  'All samples remain in the tables. These are not uniformly idle-host causal estimates;',
                  'small gains require a separate quiet-host confirmation. See CONTENTION.md for the retained observation.', '',
                  f'Contention note SHA-256: `{hashlib.sha256(contention_note).hexdigest()}`.', '']
    for metric, title in [('engine_ms', 'Engine query elapsed time'), ('cli_ms', 'Standalone CLI elapsed time')]:
        lines += [f'## {title}', '',
                  '| Flow | Main | CAS sync | CAS async | Paired async minus sync | Paired async minus main |',
                  '| --- | ---: | ---: | ---: | ---: | ---: |']
        for flow, label in FLOWS.items():
            measured = {a: values(a, flow, lambda s: s[metric]) for a in ARMS}
            paired = [median([x - y for x, y in zip(measured['async'], measured[a])]) for a in ('both', 'main')]
            cells = [*(median(measured[a]) for a in ARMS), *paired]
            lines.append('| ' + label + ' | ' + ' | '.join(f'{v:.3f}' for v in cells) + ' |')
        lines.append('')
    lines += ['Negative paired differences mean faster. Paired medians are not differences of medians.', '',
              '## Range and paired direction', '',
              'No outliers are removed. At n=6 nearest-rank p95 is the maximum, not a stable tail estimate.', '',
              '| Flow | Metric | Main min–max | CAS sync min–max | CAS async min–max | Async faster than sync / main |',
              '| --- | --- | ---: | ---: | ---: | ---: |']
    for flow in FLOWS:
        for metric in ('engine_ms', 'cli_ms'):
            v = {a: values(a, flow, lambda s: s[metric]) for a in ARMS}
            ranges = [f'{min(v[a]):.3f}–{max(v[a]):.3f}' for a in ARMS]
            wins = [sum(x < y for x, y in zip(v['async'], v[a])) for a in ('both', 'main')]
            lines.append(f'| {FLOWS[flow]} | {metric} | ' + ' | '.join(ranges) + f' | {wins[0]}/6; {wins[1]}/6 |')
    lines += ['', '## Observed phase durations', '',
              'Per-class median elapsed unions. Nested rows overlap their parent: do not sum this table.',
              'Zero means the operation was absent or below rounding, not missing validation.', '',
              '| Flow | Phase | Main | CAS sync | CAS async |', '| --- | --- | ---: | ---: | ---: |']
    for flow in DETAIL_FLOWS:
        for phase, label in PHASES:
            cells = [typical(a, flow, lambda s: s['class_ms'].get(phase, 0)) for a in ARMS]
            lines.append(f'| {FLOWS[flow]} | {label} | ' + ' | '.join(f'{v:.3f}' for v in cells) + ' |')
    lines += ['', '## Sender walk breakdown', '',
              'The main source-tree walk is selected by entry count. These are wall-work counters, not CPU time.',
              'Enumeration includes initial filesystem metadata work and scheduling. Sending includes transport',
              'backpressure. Callback Info is not the total cost of stat. The four buckets partition each sample;',
              'independently computed medians need not add exactly.', '',
              '| Flow | Version | Entries | Walk | Enumerate/filter | Callback Info | Bookkeeping | Send stats |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    fields = ('walk_ns', 'enumerate_filter_ns', 'entry_info_ns', 'packet_bookkeeping_ns', 'stat_send_ns')
    for flow in DETAIL_FLOWS:
        for arm in ARMS:
            walks = values(arm, flow, lambda s: max(s['client_walks'], key=lambda w: w['entries']))
            times = [median(w[key] for w in walks) / 1e6 for key in fields]
            lines.append(f'| {FLOWS[flow]} | {arm} | {median(w["entries"] for w in walks):.0f} | '
                         + ' | '.join(f'{v:.3f}' for v in times) + ' |')
    lines += ['', '## Asynchronous admission and cache readiness', '',
              'Admission is optional work after immutable result creation. This is moved work, not eliminated work.',
              'Times below include zero for runs that needed no admission; failed outcomes are listed separately.', '',
              '| Flow | Runs with background work | Background duration | Remaining after query | Remaining after CLI | Failed outcomes |',
              '| --- | ---: | ---: | ---: | ---: | --- |']
    for flow in FLOWS:
        admissions = values('async', flow, lambda s: s['admission'])
        counts = sum(a['background_roots'] > 0 for a in admissions)
        times = [median(a[k] for a in admissions) for k in
                 ('background_elapsed_ms', 'remaining_after_query_ms', 'remaining_after_cli_ms')]
        failures = [(r, kind, outcome) for r, a in enumerate(admissions, 1)
                    for kind in ('background_outcomes', 'handoff_outcomes')
                    for outcome in a[kind] if outcome != 'ok']
        lines.append(f'| {FLOWS[flow]} | {counts}/6 | ' + ' | '.join(f'{v:.3f}' for v in times)
                     + ' | ' + (json.dumps(failures) if failures else 'none') + ' |')
    lines += ['', '## Validity and remaining gates', '',
              f'- {len(report["readbacks"])} complete tree readbacks, first round across all versions and four changed trees.',
              '- Source manifests, mtimes and content-digest relations checked for every timed import; all owned fixtures restored.',
              '- All 18 owned engines stopped after their flows. Raw evidence and volumes retained.',
              '- Full native profiles are in runtime directories. RESULTS.json records hashes, receipt paths and summaries.',
              '- No raw events filtered; foreground stays inside CLI timing. Only explicit admission roots can outlive it.',
              '- Async whole-dump what-if rankings lack launch causality: independent roots remain fixed during replay.',
              '  Baseline reconstruction passes, but those theoretical savings are not foreground speedup predictions.',
              '- Validation/draining separates commands. Immediate-next-request overlap and sustained throughput are not measured.',
              '- The CLI timeout wait can quantize observed completion by roughly 50 ms; tiny CLI differences are not precise wins.',
              '- Profile-disabled confirmation, real GC/restart and writable-snapshot isolation are required before production.',
              '- Known promotion blocker: the current immutable Mount helper creates an additional view lease without expiry.',
              '  The expiring publisher job lease does not bound that view after a crash. See ASYNC-FOLLOWUPS.md.', '',
              'No performance fix was added while this matrix was running.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=int, default=1)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    assert 1 <= args.cohort <= 99
    folder = ROOT / f'filesync-async-matrix-r{args.cohort}'
    source = (folder / 'RESULTS.json').read_bytes()
    note_path = folder / 'CONTENTION.md'
    note = note_path.read_bytes() if note_path.exists() else None
    output = render(json.loads(source), hashlib.sha256(source).hexdigest(), note)
    if args.write:
        with (folder / 'DETAILS.md').open('x') as stream:
            stream.write(output)
    print(output)


if __name__ == '__main__':
    main()
