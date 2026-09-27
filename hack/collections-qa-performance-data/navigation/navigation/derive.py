"""Offline numeric-only evidence. Does not execute any CLI or contact any service."""
from pathlib import Path
import collections
import importlib.util
import json
import statistics
import sys

LAB = Path('/tmp/collections-perf/engine-allocation-round2')
SRC = LAB / 'navigation-generate-v1'
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
import experiment as x
spec = importlib.util.spec_from_file_location('exit_tail', LAB / 'derive-exit-tail.py')
exit_tail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exit_tail)
ALLOWED_CLASSES = frozenset((
    'session.query', 'CALL_EXEC', 'LAZY', 'CACHE_HIT', 'exec.run', 'exec.runContainer', 'exec.processRun',
    'git.publicAdvertisement', 'dagql.preselect', 'dagql.publishResult', 'Query.typeDef',
    'TypeDef.withOptional', 'TypeDef.withFunction', 'ModuleSource.asModule', 'ModuleSource.moduleTypes',
    'runModuleDefInSDK', 'moduleSourceAsModule', 'Dang.ModuleTypes', 'Dang.parse', 'Dang.eval',
    'Interface.FieldSpecs', 'Container.withExec', 'Container.withFile', 'Directory.withFile',
))
rows = json.loads((SRC / 'results.json').read_text())
assert len(rows) == 25 and all(row['correct'] for row in rows)
assert sum(row['production'] for row in rows) == 20
restoration = json.loads((SRC / 'fixture-validation.json').read_text())
assert restoration['native_full_fixture_restored'] and restoration['greetings_full_fixture_unchanged']
ordinary, diagnostics, local = {}, [], {}
for flow in ('workspace-files', 'artifacts', 'generators', 'generate-warm', 'generate-edit'):
    selected = [row for row in rows if row['phase'] == 'ordinary' and row['flow'] == flow]
    assert len(selected) == 3 and not any(row['profile'] or row['diagnostic'] for row in selected)
    samples = [row['seconds'] for row in selected]
    ready = [row['file_visible_seconds'] for row in selected]
    tails = [row['seconds'] - row['file_visible_seconds'] for row in selected if row['file_visible_seconds'] is not None]
    ordinary[flow] = {
        'n': 3, 'samples_seconds': samples, 'median_seconds': statistics.median(samples),
        'minimum_seconds': min(samples), 'maximum_seconds': max(samples),
        'file_visible_samples_seconds': ready,
        'median_file_visible_seconds': statistics.median(ready) if all(value is not None for value in ready) else None,
        'file_to_exit_samples_seconds': tails,
        'median_file_to_exit_seconds': statistics.median(tails) if tails else None,
        'file_visibility_poll_ms': 5 if tails else None,
        'file_visibility_censored_samples': sum(row['file_visibility_censored_at_exit'] for row in selected),
        'engine_cpu_seconds': [row['engine_cpu_seconds'] for row in selected],
        'engine_written_bytes': [row['engine_written_bytes'] for row in selected],
        'host_psi_delta_us': [row['host_psi_delta_us'] for row in selected],
    }
    sample = next(row for row in rows if row['flow'] == flow and row['phase'] == 'local-correctness')
    local[flow] = {'n': 1, 'seconds': sample['seconds'], 'file_visible_seconds': sample['file_visible_seconds'], 'correct': sample['correct'], 'comparison': 'untimed-for-ordinary-statistics correctness warmup; not a matched Cloud/local distribution'}
    row = next(row for row in rows if row['flow'] == flow and row['phase'] == 'diagnostic')
    directory = SRC / ('diagnostic-0-' + flow)
    analyzed = exit_tail.analyze(dict(row, variant='candidate'), directory)
    analyzed['file_visible_seconds'] = row['file_visible_seconds']
    analyzed['file_to_exit_seconds'] = row['seconds'] - row['file_visible_seconds'] if row['file_visible_seconds'] is not None else None
    grouped = collections.defaultdict(list)
    unknown = 0
    with (directory / 'run.wcprof').open() as stream:
        header = json.loads(next(stream))
        for line in stream:
            operation = json.loads(line)
            if operation['e'] != 'op':
                continue
            category = header['strings'][operation.get('c', 0)]
            if category in ALLOWED_CLASSES:
                grouped[category].append((operation['s'], operation['d']))
            else:
                unknown += 1
    analyzed['operation_classes_allowlisted'] = {
        category: {'count': len(intervals), 'summed_ms': sum(end-start for start,end in intervals)/1e6,
                   'maximum_ms': max(end-start for start,end in intervals)/1e6,
                   'union_ms': exit_tail.union(intervals)/1e6}
        for category, intervals in sorted(grouped.items())
    }
    analyzed['operations_outside_class_allowlist'] = unknown
    assert analyzed['wcprof']['open'] == 0 and analyzed['wcprof']['dropped'] == 0
    assert all(request['kind'] in ('cloud.traces','cloud.logs','cloud.metrics') for request in analyzed['requests'])
    assert all(all(isinstance(value, int) for value in request['numeric_http_values'].values()) for request in analyzed['requests'])
    diagnostics.append(analyzed)

analysis = {
    'correctness': {'commands': 25, 'ordinary_cloud': 15, 'diagnostic_cloud': 5, 'local_warmups': 5,
                    'all_correct': True, 'both_fixtures_restored': True},
    'ordinary': ordinary, 'diagnostics': diagnostics, 'local_warmups_not_comparison': local,
    'provenance_sha256': {name: x.sha(SRC/name) for name in ('results.json','summary.json','fixture-validation.json','provenance.json','driver.py.txt')},
    'analyzer_sha256': x.sha(LAB/'derive-exit-tail.py'),
    'limits': ['Retained candidate engine, experimental SDK stack, normal production Cloud telemetry; no cold claim.',
               'Three ordinary repetitions per flow; diagnostic/profile rows excluded from medians.',
               'Native generation is one Dang @generate, not SDK generation or a large project build.',
               'File readiness polled at 5 ms; process exit obtained by blocking waitpid.',
               'Nested phase/class durations overlap; summed operation time is not critical-path latency.',
               'HTTP hooks observe CLI-owned uploads only, not engine-owned Cloud uploads.',
               'First-byte wait includes network and receiver work; connection acquisition is not pure queue wait.',
               'Numeric counter brackets include process-wide/background CPU and I/O; no attribution from a single write spike.',
               'Raw profiles/string tables, outputs, identifiers and payloads are excluded from this evidence directory.'],
}
x.write(OUT/'analysis.json', analysis)
commands = {'workspace-files': '`dagger ws ls` — greetings-api', 'artifacts': '`dagger list -a` — greetings-api', 'generators': '`dagger generate -l` — greetings-api', 'generate-warm': '`dagger -y generate` — native fixture, unchanged input', 'generate-edit': 'Unique input edit → `dagger -y generate` — native fixture'}
lines = [
'# Navigation and generation timings', '',
'With normal production Cloud telemetry, the generated file becomes available within **296 ms warm** and **379 ms after a new input edit** in this small native fixture. Full CLI exit remains **726 ms** and **925 ms** respectively. This clears the 500 ms target for file availability here, not for complete command exit or general SDK generation.', '',
'Current candidate engine with the existing experimental SDK stack; three ordinary repetitions per flow, unchanged CLI, retained caches. Five local correctness warmups and five separate diagnostic/profile commands are excluded from these medians.', '',
'| User operation | Ordinary samples (ms) | Median exit (ms) | Median file ready (ms) | Median file→exit (ms) |',
'| --- | --- | ---: | ---: | ---: |',
]
for flow, values in ordinary.items():
    ready = values['median_file_visible_seconds']; tail = values['median_file_to_exit_seconds']
    lines.append('| '+commands[flow]+' | '+' / '.join(f'{s*1000:.0f}' for s in values['samples_seconds'])+f' | {values["median_seconds"]*1000:.0f} | '+(f'{ready*1000:.0f}' if ready is not None else '—')+' | '+(f'{tail*1000:.0f}' if tail is not None else '—')+' |')
lines += ['', 'The native generator copies an ordinary workspace input into a generated output through a Changeset. Each measured edit uses previously unseen input bytes, and each generation starts with the output removed. Every resulting file exactly matched the current input. This is an actual user-facing generation command, but **not a Go/TypeScript SDK generator benchmark**.', '',
'All 25 commands passed. Workspace entries, artifact identities and generator identities were checked, listing output matched normalized local correctness runs, and both fixtures were restored. File availability uses 5 ms polling; full exit uses blocking waitpid.', '',
'## Separate diagnostics', '',
'Each row below is one instrumented/profiled invocation, not part of the ordinary median. The shutdown phases are nested: do not add engine close to shutdown HTTP, or telemetry close to provider shutdown.', '',
'| Flow | CLI exit (ms) | Query union (ms) | After command callback (ms) | Engine shutdown HTTP (ms) | CLI telemetry close (ms) | CLI HTTP uploads |',
'| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for row in diagnostics:
    phase=row['phase_ms']
    lines.append(f'| {row["flow"]} | {row["seconds"]*1000:.0f} | {row["wcprof"]["query_union_ms"]:.0f} | {row["cli_after_command_ms"]:.0f} | {phase.get("engine.shutdown_http",0):.0f} | {phase.get("cli.telemetry_close",0):.0f} | {len(row["requests"])} |')
lines += ['', 'The complete numeric phase breakdown, exact samples, HTTP counters and allowlisted operation-class aggregates are in `analysis.json`. All five wcprof files report zero open operations and zero dropped events. Request counts include only exact `cloud.traces`, `cloud.logs` and `cloud.metrics` HTTP rows; exporter wrapper spans are excluded.', '',
'The 5 local warmups are setup/correctness evidence, not a controlled production-versus-local benchmark. These retained-volume measurements make no cold-start claim. Raw outputs, wcprof string tables and payloads remain private. CPU, I/O and operation durations overlap with wall time and cannot be added as hypothetical savings.', '']
(OUT/'report.md').write_text('\n'.join(lines))
print(json.dumps({'ordinary_medians_ms':{key:round(value['median_seconds']*1000,2) for key,value in ordinary.items()}, 'diagnostics':[{ 'flow':row['flow'],'phase_ms':row['phase_ms'],'wcprof':row['wcprof'],'http_uploads':len(row['requests'])} for row in diagnostics]},indent=2))
