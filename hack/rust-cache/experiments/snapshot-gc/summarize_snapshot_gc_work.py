from pathlib import Path
import json
import statistics

root = Path('/tmp/rust-cache-sipsma-review/snapshot-gc-causal')
rows = json.loads((root / 'paired/samples.json').read_text())
measured = [r for r in rows if not r['preparation']]
scenarios = ['idle', 'account', 'account-lazy', 'collect']
summary = {}
for scenario in scenarios:
    selected = [r for r in measured if r['scenario'] == scenario]
    baseline = {r['pair']: r for r in measured if r['scenario'] == 'idle'}
    paired = [r['command_seconds'] - baseline[r['pair']]['command_seconds'] for r in selected]
    summary[scenario] = dict(
        samples=len(selected),
        **{name: statistics.median(r[name] for r in selected)
           for name in ['command_seconds', 'case_seconds', 'drain_seconds']},
        median_paired_command_penalty_seconds=statistics.median(paired),
        slower_pairs=sum(n > 0 for n in paired),
        command_cpu_seconds={scope: statistics.median(r['command_cpu_seconds'][scope] for r in selected)
                             for scope in ['engine', 'exec', 'docker_total']},
        max_stall_fraction={name: max(r['stall_fraction'][name] for r in selected)
                            for name in selected[0]['stall_fraction']},
    )
    for r in selected:
        assert r['after_drain']['snapshot_exists'] is False
        assert r['after_command']['snapshot_exists'] is (scenario != 'collect')
        if r['job']:
            if 'complete' in r['job']:
                assert r['job']['complete']
            begin = max(r['command_unix_start'], r['job']['request_started_unix'])
            end = min(r['command_unix_start'] + r['command_seconds'], r['job']['request_finished_unix'])
            assert end > begin

profiles = {}
for path in sorted((root / 'pilot').glob('*.ndjson')):
    with path.open() as stream:
        header = json.loads(next(stream))
        events = [json.loads(line) for line in stream if line.strip()]
    ops = [r for r in events if r['e'] == 'op']
    assert header['dropped_events'] == 0
    assert all(r.get('d', 0) > 0 for r in ops)
    selected = []
    for op in ops:
        cls = header['strings'][op['c']]
        if (cls == 'Host.directory' and op['k'] == 'call_exec') or cls in ['gc.diagnostic.collect', 'gc.diagnostic.account', 'snapshot.collect']:
            selected.append(dict(class_name=cls, kind=op['k'], milliseconds=(op['d'] - op['s']) / 1e6))
    profiles[path.name] = dict(ops=len(ops), dropped_events=0, open_ops=0, selected_operations=selected)

result = dict(
    comparisons=summary,
    maximum_metadata_estimated_bytes=max(r['after_command']['metadata_estimate']['EstimatedBytes'] for r in rows),
    configured_metadata_limit_bytes=rows[0]['after_command']['metadata_max_bytes'],
    longest_post_command_drains_seconds=sorted([r['drain_seconds'] for r in measured], reverse=True)[:5],
    profiles=profiles,
    scope='Controlled concurrent work on the same edited-command history. Ordinary containerd collection is deferred in every arm and drained after each command; dagql pruning remains enabled. This does not benchmark a production scheduling change or prove the cause of earlier 15-second stalls.',
)
(root / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'profiles'}, indent=2))
