import json
import os
from pathlib import Path
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
tree = Path('/tmp/dagger-telemetry-batch-metadata')
go = '/home/dagger/.local/bin/go'
env = dict(os.environ, GOMAXPROCS='8')


def run(command, name, expected=0, cwd=tree, extra_env=None):
    with (base / name).open('w') as output:
        result = subprocess.run(command, cwd=cwd, env=extra_env or env,
                                stdout=output, stderr=subprocess.STDOUT)
    assert result.returncode == expected, (name, result.returncode)
    print('PASS', name, flush=True)


uncloned = (tree / 'engine/clientdb/log.go').read_text().replace(
    'proto.Clone(decoded.pb).(*otlpcommonv1.InstrumentationScope)', 'decoded.pb')
old = base / 'batch-metadata-uncloned-log.go'
old.write_text(uncloned)
overlay = base / 'batch-metadata-uncloned-overlay.json'
overlay.write_text(json.dumps(dict(Replace={str(tree / 'engine/clientdb/log.go'): str(old)})))
run([go, 'test', '-buildvcs=false', '-overlay=' + str(overlay), '-count=1',
     '-run=^TestLogsToPBPreservesBatchMetadata$', './engine/clientdb'],
    'batch-metadata-ownership-before.log', expected=1)
assert 'changed' in (base / 'batch-metadata-ownership-before.log').read_text()
run([go, 'test', '-buildvcs=false', '-race', '-count=1', './engine/clientdb'],
    'batch-metadata-clientdb-race-final.log')
run([go, 'test', '-buildvcs=false', '-race', '-count=1', './engine/server',
     '-run=^(TestCloudForwarder.*|TestCloudForwardersStopAll|TestCloudPublishedRow|TestSessionCloudForwarderDrainsAfterTeardown|TestSessionPublishesTelemetryToCloud|TestSessionDeliversCallSpansToStoreAndCloud|TestTelemetryStreamsConfirmCloudPublishing|TestPostedTelemetryReachesCloudOnce|TestCallPayloadReachesCloudOnce|TestTracesHandlerToleratesMissingResource|TestLogsHandlerToleratesMissingResourceAndBody)$'],
    'batch-metadata-forwarding-race-final.log')
run([go, 'test', '-buildvcs=false',
     '-overlay=' + str(base / 'batch-metadata-benchmark-after-overlay.json'),
     '-run=^$', '-bench=^BenchmarkLogMetadataBatch$', '-benchtime=500ms',
     '-count=5', './engine/clientdb'], 'batch-metadata-benchmark-after-final.log')
run(['python3', str(base / 'prepare_batch_metadata_engine.py')],
    'batch-metadata-prepare-final.log', cwd=base)
run([go, 'build', '-buildvcs=false', '-mod=readonly',
     '-overlay=' + str(base / 'batch-metadata-engine-overlay.json'),
     '-modfile=' + str(base / 'dang-content-key.go.mod'), '-o',
     str(base / 'dagger-engine-batch-metadata'), './cmd/engine'],
    'batch-metadata-engine-build-final.log', cwd=Path('/tmp/dagger-filesync-snapshot-seeds'),
    extra_env=dict(env, CGO_ENABLED='0'))
