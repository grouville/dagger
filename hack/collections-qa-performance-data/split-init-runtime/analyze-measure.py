"""Sanitize the completed, bounded split-init trial to numeric/source evidence."""
from pathlib import Path
import hashlib, json, shutil, statistics

HERE = Path(__file__).resolve().parent
RAW = HERE / 'measure/results-v1'
OUT = HERE / 'measure-evidence'
OUT.mkdir(exist_ok=True)
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')

rows = json.loads((RAW / 'results.json').read_text())
restore = json.loads((RAW / 'restoration.json').read_text())
assert len(rows) == 36 and all(row['correct'] for row in rows)
assert all(restore[key] for key in ('fixtures_restored', 'original_engine_binary_untouched',
    'original_init_binary_untouched', 'original_engine_stopped', 'retained_volume_preserved',
    'temporary_container_removed'))
assert restore['cloud_commands'] == 0 and restore['cleanup_error_type'] is None
keys = ('variant', 'flow', 'phase', 'block', 'profile', 'expected_failure', 'input_sha256',
    'app_main_sha256', 'native_module_sha256', 'seconds', 'exit_code', 'correct',
    'stdout_sha256', 'timed_out', 'unexpected_cloud_link', 'file_visible_seconds',
    'output_already_current', 'file_visible_censored_at_exit', 'file_poll_ms', 'file_polls',
    'process_tree_user_seconds', 'process_tree_system_seconds', 'engine_cpu_seconds',
    'engine_written_bytes', 'counter_bracket_seconds', 'host_psi_delta_us')
write('samples.json', [{'index': i, **{key: row[key] for key in keys if key in row}}
    for i, row in enumerate(rows)])

summary = {}
for phase in ('warm', 'fresh-edit'):
    for flow in sorted({row['flow'] for row in rows if row['phase'] == phase}):
        group = {}
        for variant in ('baseline', 'candidate'):
            sample = [row for row in rows if row['phase'] == phase and row['flow'] == flow
                and row['variant'] == variant and not row['profile']]
            values = [1000 * row['seconds'] for row in sample]
            visible = [1000 * row['file_visible_seconds'] for row in sample
                if row['file_visible_seconds'] is not None]
            group[variant] = {'n': len(sample), 'blocks': [row['block'] for row in sample],
                'milliseconds': values, 'median_ms': statistics.median(values),
                'file_visible_ms': visible,
                'file_visible_median_ms': statistics.median(visible) if visible else None,
                'process_tree_cpu_ms': [1000 * (row['process_tree_user_seconds'] +
                    row['process_tree_system_seconds']) for row in sample],
                'engine_cpu_ms': [1000 * row['engine_cpu_seconds'] for row in sample]}
        group['median_delta_ms'] = group['candidate']['median_ms'] - group['baseline']['median_ms']
        group['change_percent'] = 100 * group['median_delta_ms'] / group['baseline']['median_ms']
        # Match samples within the adjacent AB and BA blocks, without claiming independence.
        differences = []
        for b, c in ((0, 1), (3, 2)):
            base = [row for row in rows if row['phase'] == phase and row['flow'] == flow and row['block'] == b]
            cand = [row for row in rows if row['phase'] == phase and row['flow'] == flow and row['block'] == c]
            assert len(base) == len(cand)
            differences.extend(1000 * (y['seconds'] - x['seconds']) for x, y in zip(base, cand))
        group['adjacent_block_sample_deltas_ms'] = differences
        group['adjacent_block_sample_delta_median_ms'] = statistics.median(differences)
        group['candidate_faster_count'] = sum(value < 0 for value in differences)
        summary[phase + '/' + flow] = group
write('summary.json', summary)
write('restoration.json', restore)

def union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged) / 1e6
def stats(ops):
    return {'count': len(ops), 'inclusive_sum_ms': sum(op['d'] - op['s'] for op in ops) / 1e6,
        'union_ms': union((op['s'], op['d']) for op in ops),
        'maximum_ms': max([op['d'] - op['s'] for op in ops], default=0) / 1e6,
        'error_count': sum(op.get('o') == 'error' for op in ops)}

profiles = {}
labels = ('session.query', 'Workspace.artifacts', 'Artifacts.__itemsJSON', 'exec.processRun',
    'git.publicAdvertisement', 'moduleSource.loadContext', 'moduleSource.loadSDK',
    'Container.withFile', 'Go.modules', 'Gomod.modules', 'GoModule.tests', 'Address.container')
call_labels = {'Workspace.artifacts', 'Artifacts.__itemsJSON', 'Container.withFile',
    'Go.modules', 'Gomod.modules', 'GoModule.tests', 'Address.container'}
for path in sorted(RAW.glob('*/run.wcprof.private')):
    with path.open() as stream:
        header = json.loads(next(stream))
        ops = [op for line in stream if line.strip() and (op := json.loads(line)).get('e') == 'op']
    variant = path.parent.name.rsplit('-', 1)[-1]
    assert variant in ('baseline', 'candidate') and variant not in profiles
    name = lambda op: header['strings'][op.get('c', 0)]
    origin = min(op['s'] for op in ops)
    def records(label):
        return [op for op in ops if name(op) == label and
            (label not in call_labels or op['k'] == 'call_exec')]
    def times(op):
        return {'start_ms': (op['s'] - origin) / 1e6, 'end_ms': (op['d'] - origin) / 1e6,
            'duration_ms': (op['d'] - op['s']) / 1e6}
    catalog, expansion = records('Workspace.artifacts'), records('Artifacts.__itemsJSON')
    assert len(catalog) == len(expansion) == 1
    process = records('exec.processRun')
    entry = {'profile_sha256': sha(path), 'open_operations': len(header.get('open_ops', [])),
        'dropped_events': header['dropped_events'], 'phases': {label: stats(records(label)) for label in labels},
        'processes': [times(op) for op in sorted(process, key=lambda op: op['s'])],
        'catalog': times(catalog[0]), 'expansion': times(expansion[0])}
    for label, enclosing in (('catalog', catalog[0]), ('expansion', expansion[0])):
        entry['processes_enclosed_in_' + label] = stats([op for op in process
            if op['s'] >= enclosing['s'] and op['d'] <= enclosing['d']])
    assert entry['open_operations'] == entry['dropped_events'] == 0
    profiles[variant] = entry
assert len(profiles) == 2
write('profile-phases.json', {'arms': profiles, 'notes': [
    'One separately profiled, fully primed listing per arm, baseline then candidate.',
    'exec.processRun includes command execution; it does not isolate PID1 startup.',
    'Inclusive spans overlap. Interval unions within a label are not additive critical-path savings.',
    'Process ordinals are start order, not matched module identity. Profiles are excluded from ordinary timings.']})

prov = json.loads((RAW / 'provenance.json').read_text())
safe = {key: prov[key] for key in ('driver_sha256', 'frozen_runtime_manifest_sha256',
    'frozen_inputs_sha256', 'fixture_inventory_sha256', 'runtime_manifest', 'helpers_both_arms',
    'cli', 'fixtures_before', 'flows', 'stage', 'commands_cap', 'cloud_commands', 'cache_boundary',
    'timing', 'scope', 'limits')}
safe['order'] = ['baseline', 'candidate', 'candidate', 'baseline']
safe['ambient_width_caveat'] = 'Existing /tmp fixture ancestry is wide. Both arms use the same path and explicit parent-metadata transport; this trial does not generalize all checkout layouts.'
write('provenance.json', safe)
for filename in ('runtime.py', 'frozen-runtime-manifest.json', 'frozen-inputs.json', 'fixture-inventory.json',
    'csv-roundtrip.json', 'prepared-hashes.json', 'analyze-measure.py'):
    shutil.copyfile(HERE / filename, OUT / filename)
write('input-hashes.json', {str(path.relative_to(HERE)): sha(path) for path in
    (HERE / 'runtime.py', RAW / 'results.json', RAW / 'restoration.json', RAW / 'provenance.json',
        HERE / 'frozen-runtime-manifest.json', HERE / 'frozen-inputs.json')})
print(json.dumps({key: {variant: round(group[variant]['median_ms'], 2)
    for variant in ('baseline', 'candidate')} for key, group in summary.items()}, indent=2))
print(json.dumps({variant: {'process_count': entry['phases']['exec.processRun']['count'],
    'process_union_ms': entry['phases']['exec.processRun']['union_ms'],
    'catalog_ms': entry['catalog']['duration_ms'], 'expansion_ms': entry['expansion']['duration_ms'],
    'query_union_ms': entry['phases']['session.query']['union_ms']}
    for variant, entry in profiles.items()}, indent=2))
