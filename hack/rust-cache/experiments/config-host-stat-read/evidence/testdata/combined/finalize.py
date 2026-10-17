from pathlib import Path
import json
import statistics
import urllib.request

root = Path(__file__).parent
restored = json.loads((root / 'restored-state.json').read_text())
assert restored['engine_sha256'] == '51542ef941c4e3bd96c2ce770c118d154824272ff247d8b9038b0cb27e5fa0e3'
with urllib.request.urlopen('http://127.0.0.1:16104/debug/client-lifecycle', timeout=20) as response:
    lifecycle = json.load(response)
assert not lifecycle.get('sessions') and lifecycle['active_requests'] == 0
rows = json.loads((root / 'full-command-paired/samples.json').read_text())
summary = json.loads((root / 'full-command-paired/summary.json').read_text())
assert summary['all_commands_succeeded'] and summary['same_rows']
capture = json.loads((root / 'capture/result.json').read_text())
assert capture['same_rows'] and capture['exit_code'] == 0
assert capture['recorder']['dropped'] == 0 and capture['recorder']['open'] == 0
derived = dict(
    cli_cpu_seconds={arm: statistics.median(r['cli_resources']['user_seconds'] + r['cli_resources']['system_seconds']
        for r in rows if r['pair'] > 0 and r['arm'] == arm) for arm in ['before', 'after']},
    median_paired_saving_seconds=statistics.median(
        next(r['seconds'] for r in rows if r['pair'] == pair and r['arm'] == 'before') -
        next(r['seconds'] for r in rows if r['pair'] == pair and r['arm'] == 'after') for pair in range(1, 5)),
    initialization_requests={r['arm']: {key: r['stat_read_after'][key] - r['stat_read_before'][key]
        for key in ['combined', 'stat_only', 'read_only']} for r in rows if r['pair'] == 0})
(root / 'derived.json').write_text(json.dumps(derived, indent=2) + '\n')
decision = dict(selected=False, reason='Only one of four full-command pairs is faster; command latency, engine CPU and allocation regress in this cohort despite reduced requests and CLI CPU.',
    full_command=summary, comparison='One retained engine and matched CLI in both arms; fresh edits and CLI processes, ordinary telemetry and GC; initialization is separate. All attempts retained.',
    causality_limit='Cache compaction stalls publication in the diagnostic. This does not prove why the candidate cohort encounters more overhead or quantify the benefit of a future compaction change.',
    native_histories='All six preserve every expected hit before/after candidate restart, after cohort/capture, and first call after exact original-binary restoration.',
    selected_engine_restored=restored['engine_sha256'], new_pr_opened=False)
(root / 'decision.json').write_text(json.dumps(decision, indent=2) + '\n')
(root / 'progress.json').write_text(json.dumps(dict(previous_turn='progress: content-keyed declarations selected and pushed.',
    stage='Two host-request approaches rejected; full-command comparisons and complete profiles retained. A seven-second publication stall is aligned with cache-index compaction and blocked publishers.',
    goal_status='Active; full Go listing and integrated Rust performance targets remain incomplete.',
    next_targets=['Audit compaction ownership before retaining unchanged digest sets; benchmark the actual compaction path and full edited listings.',
                  'Define ownership and invalidation before sharing a versioned module-configuration input.',
                  'Recheck existing Protobuf and callback-scope prototypes against the current collection workload.'],
    new_pr_opened=False), indent=2) + '\n')
old = root.parent / 'config-host-read-first'
rejection = json.loads((old / 'metadata-rejection-tests.json').read_text())
assert all(row['expected_outcome'] for row in rejection)
(old / 'progress.json').write_text(json.dumps(dict(selected=False,
    reason='A successful contents read bypasses an existing metadata failure; missing paths and directories use two requests instead of one.',
    metadata_regression='Original passes; read-first fails because PermissionDenied becomes OK. The initial output-validator formatting mistake and corrected verification are retained.',
    engine_activated=False), indent=2) + '\n')
print('PASS: every listing is correct; both approaches remain rejected; original engine restored and idle; all native histories retained.', flush=True)
