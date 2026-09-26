"""Derive shareable numeric evidence from completed local measurements only."""
from pathlib import Path
from datetime import datetime, timezone
import collections, hashlib, json, statistics

lab = Path(__file__).resolve().parent.parent
out = Path(__file__).resolve().parent
load = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def write(name, value):
    (out / name).write_text(json.dumps(value, indent=2) + '\n')

results = load(lab / 'local-v1/results.json')
manifest = load(lab / 'prepared.json')
assert len(results) == 279
assert all(r['correct'] for r in results)
assert sum(r['expected_failure'] for r in results) == 3
assert all((r['exit_code'] != 0) == r['expected_failure'] for r in results)
keys = ('variant', 'flow', 'phase', 'index', 'profile', 'seconds', 'started_unix_ns', 'exited_unix_ns', 'exit_code', 'stdout_sha256', 'correct', 'engine_allocated_bytes', 'engine_gc_cycles', 'expected_failure', 'engine_written_bytes', 'http_ready_seconds', 'cancel_to_exit_seconds', 'file_visible_seconds', 'file_visibility_poll_ms')
safe = []
for r in results:
    d = {k: r[k] for k in keys if k in r}
    d['engine_cpu_seconds'] = (r['after']['engine_cpu']['usage_usec'] - r['before']['engine_cpu']['usage_usec']) / 1e6
    d['host_psi_delta_us'] = {k: {q: r['after']['host_psi_us'][k][q] - r['before']['host_psi_us'][k][q] for q in r['before']['host_psi_us'][k]} for k in r['before']['host_psi_us']}
    d['forced_gc_delta'] = r['after']['memstats']['NumForcedGC'] - r['before']['memstats']['NumForcedGC']
    d['free_disk_before_bytes'] = r['before']['free_disk_bytes']
    d['free_disk_after_bytes'] = r['after']['free_disk_bytes']
    safe.append(d)
write('matrix-samples.json', safe)
write('matrix-summary.json', load(lab / 'local-v1/summary.json'))
paired = []
for phase, flow in sorted({(r['phase'], r['flow']) for r in results if r['phase'] in ('warm','rename','user-comment','direct-check-edit','input-edit')}):
    groups = {v: {r['index']: r for r in results if r['phase'] == phase and r['flow'] == flow and r['variant'] == v} for v in ('base','interface','combined')}
    for v in ('interface','combined'):
        indices = sorted(groups['base'])
        assert set(indices) == set(groups[v])
        deltas = [groups[v][i]['seconds'] - groups['base'][i]['seconds'] for i in indices]
        paired.append({'phase': phase, 'flow': flow, 'candidate': v, 'indices': indices, 'paired_seconds_delta': deltas, 'median_paired_seconds_delta': statistics.median(deltas)})
write('paired-deltas.json', paired)
write('restoration.json', load(lab / 'local-v1/restoration.json'))
write('startup.json', load(lab / 'local-v1/startup.json'))
provenance = {
    'scope': 'Current common experimental engine stack, not main or Kyle\'s machine; no Cloud/OTLP exporters in this local matrix.',
    'source_HEAD': manifest['builds']['base']['source_HEAD'],
    'cli_sha256': manifest['cli_sha256'],
    'base_image_id': manifest['image'],
    'engine_sha256': {v: manifest['containers'][v]['sha256'] for v in ('base','interface','combined')},
    'fixture_sha256': manifest['fixture_hashes_excluding_git_and_node_modules'],
    'blob_sha256': sorted(manifest['blobs'].values()),
    'driver_sha256': sha(lab / 'local-v1/driver.py.txt'),
    'source_evidence_sha256': {str(p.relative_to(lab)): sha(p) for p in (lab/'prepared.json',lab/'local-v1/results.json',lab/'local-v1/summary.json',lab/'local-v1/restoration.json',lab/'fresh-edit-profiles-v1/results.json',lab/'fresh-edit-profiles-v1/go-build-ancestry.json')},
}
write('provenance.json', provenance)
fresh = load(lab / 'fresh-edit-profiles-v1/results.json')
assert len(fresh) == 2 and all(r['correct'] and r['profile'] and r['exit_code'] == 0 for r in fresh)
assert len({r['source_sha256'] for r in fresh}) == 2
write('fresh-edit-profiles.json', fresh)
ancestry = load(lab / 'fresh-edit-profiles-v1/go-build-ancestry.json')
write('go-build-ancestry.json', ancestry)
write('fresh-edit-restoration.json', load(lab / 'fresh-edit-profiles-v1/restoration.json'))
for name, source in [('interface-microbench-summary.json',Path('/tmp/collections-perf/sdk-edit-audit/interface-signatures/lazy-benchmark-summary.json')),('dang-microbench-summary.json',Path('/tmp/collections-perf/sdk-edit-audit/dang-clone-leaves/benchmark-summary.json'))]:
    value = load(source)
    assert all(set(row) == {'case','baseline','candidate','timeRatio','bytesRatio'} for row in value)
    write(name, value)
verification = {
    'derived_at_utc': datetime.now(timezone.utc).isoformat(),
    'matrix_commands': len(results),
    'successful_exit_commands': sum(r['exit_code'] == 0 for r in results),
    'expected_nonzero_commands': sum(r['expected_failure'] for r in results),
    'all_expected_outcomes': True,
    'commands_by_phase': dict(collections.Counter(r['phase'] for r in results)),
    'commands_by_variant': dict(collections.Counter(r['variant'] for r in results)),
    'commands_by_flow': dict(collections.Counter(r['flow'] for r in results)),
    'profiled_matrix_commands': sum(r['profile'] for r in results),
    'forced_gc_deltas': sorted({r['forced_gc_delta'] for r in safe}),
    'minimum_observed_free_disk_bytes': min(min(r['free_disk_before_bytes'],r['free_disk_after_bytes']) for r in safe),
    'maximum_per_command_engine_written_bytes': max(r['engine_written_bytes'] for r in safe),
    'existing_fixture_restored': load(lab/'local-v1/restoration.json')['existing_fixture_files_preserved'],
    'created_fixture_files': load(lab/'local-v1/restoration.json')['created_fixture_files'],
    'fresh_profile_commands_separate_from_matrix': len(fresh),
    'fresh_profiles_complete': all(x['open'] == 0 and x['dropped'] == 0 and x['started_before_cli'] == 0 and x['ended_after_cli'] == 0 for x in ancestry.values()),
    'historical_cache_contamination_established': False,
    'no_broad_combined_wall_time_claim': True,
    'withfile_result_status': 'pending separate trial; not included in these completed aggregates',
    'raw_stdout_stderr_profiles_cloud_outputs_archived': False,
}
write('verification.json', verification)
print(json.dumps({'matrix_commands':len(results),'fresh_profile_commands':len(fresh),'archive_directory':str(out),'all_expected_outcomes':True}))
