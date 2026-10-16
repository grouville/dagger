from pathlib import Path
import hashlib
import json
import subprocess

root = Path('/tmp/rust-cache-sipsma-review/snapshot-gc-causal')
engine = 'dagger-rust-parser-state-pool-oct14'
focused = '^(TestLocalCacheMetadataPruneDoesNotCollectSnapshots|TestSnapshotGarbage.*|TestGCLocked.*|TestExplicitPrune.*|TestManual.*Prune.*|TestLocalCacheStateTakesTheBuiltinStore|TestGCSessionCompletionClearsMetadataPruneBlock|TestScheduledGCTrimsImportedMetadataWithoutPersistenceReset)$'
diagnostic = '^(TestSnapshotCollectionDiagnosticPreservesPending|TestSnapshotCollectionDiagnosticDrainPreservesLeasedSnapshot|TestSnapshotGarbageCollectsReleasedSnapshots|TestGCLockedCollectsGarbageWhenPruneRemovesNothing|TestGCLockedCollectsGarbageWithGCDisabled|TestExplicitPruneCollectsReleasedSnapshots|TestGCLockedPrunesMetadataWithoutWorkerDiskPolicies|TestGCLockedDiskStatFailureDoesNotSuppressMetadataPrune)$'
results = []
for arm, selection, expected in [
    ('before', '^TestLocalCacheMetadataPruneDoesNotCollectSnapshots$', 1),
    ('after', focused, 0), ('after-race', focused, 0), ('diagnostic', diagnostic, 0),
]:
    binary = root / ('server.test' if arm == 'diagnostic' else f'upstream-{arm}.test')
    target = f'/tmp/verify-snapshot-gc-{arm}.test'
    subprocess.run(['docker', 'cp', str(binary), engine + ':' + target], check=True)
    command = ['docker', 'exec', engine, 'env', '-u', '_DAGGER_TEST_REMOTE_CACHE_FIXTURE_ROOT',
               'GOMAXPROCS=8', target, '-test.run', selection, '-test.count=1', '-test.v']
    logfile = root / (f'upstream-{arm}-tests.log' if arm != 'diagnostic' else 'diagnostic-fixture-env-unset-tests.log')
    with logfile.open('w') as output:
        process = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    text = logfile.read_text()
    assert process.returncode == expected, (arm, process.returncode)
    if arm == 'before':
        assert text.count('Should be zero, but was 1') == 2
    passed = sum(line.startswith('--- PASS:') for line in text.splitlines())
    if arm in ['after', 'after-race']:
        assert passed == 17
    if arm == 'diagnostic':
        assert passed == 8
    results.append(dict(arm=arm, expected_exit=expected, actual_exit=process.returncode,
                        top_level_passes=passed, command=command,
                        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()))
    print(arm, 'expected regression failure' if expected else 'PASS', passed, flush=True)
(root / 'validation.json').write_text(json.dumps(results, indent=2) + '\n')
