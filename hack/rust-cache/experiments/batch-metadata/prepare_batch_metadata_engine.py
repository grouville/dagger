import json
from pathlib import Path

base = Path('/tmp/rust-cache-sipsma-review')
engine = Path('/tmp/dagger-filesync-snapshot-seeds')
candidate = Path('/tmp/dagger-telemetry-batch-metadata')
overlay = json.loads((base / 'snapshot-completion-engine-overlay.json').read_text())


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:80]
    return text.replace(old, new, 1)


span = (base / 'attribute-array-diagnostic-span.go').read_text()
original_span = (engine / 'engine/clientdb/span.go').read_text()
candidate_span = (candidate / 'engine/clientdb/span.go').read_text()
prefix = original_span[original_span.index('type readOnlySpan struct'):original_span.index('var _ sdktrace.ReadOnlySpan')]
candidate_prefix = candidate_span[candidate_span.index('type readOnlySpan struct'):candidate_span.index('var _ sdktrace.ReadOnlySpan')]
span = replace_once(span, prefix, candidate_prefix)
for start, end in [('func (ros *readOnlySpan) Resource()', '// InstrumentationLibrary'),
                   ('func (ros *readOnlySpan) InstrumentationScope()', '// Ended')]:
    old = original_span[original_span.index(start):original_span.index(end)]
    new = candidate_span[candidate_span.index(start):candidate_span.index(end)]
    span = replace_once(span, old, new)
span = replace_once(span, '\treturn result\n}',
                    '\trecordSpanBatchMetadata(len(spans), len(resources), len(scopes))\n\treturn result\n}')
(base / 'batch-metadata-diagnostic-span.go').write_text(span)

log = (candidate / 'engine/clientdb/log.go').read_text()
log = replace_once(log, 'func LogsToPB(dbLog []Log) []*otlplogsv1.ResourceLogs {',
                   'func LogsToPB(dbLog []Log) []*otlplogsv1.ResourceLogs {\n\tif !BatchMetadataEnabled() { return legacyLogsToPB(dbLog) }')
log = replace_once(log, '\treturn rss\n}',
                   '\trecordLogBatchMetadata(len(dbLog), len(resourceCache), len(scopeCache))\n\treturn rss\n}')
(base / 'batch-metadata-diagnostic-log.go').write_text(log)
legacy_log = (engine / 'engine/clientdb/log.go').read_text().replace('func LogsToPB(', 'func legacyLogsToPB(', 1)
(base / 'batch-metadata-legacy-log.go').write_text(legacy_log)

server = (engine / 'engine/server/telemetry.go').read_text()
candidate_server = (candidate / 'engine/server/telemetry.go').read_text()
start = server.index('func fetchSpanBatch(')
end = server.index('// fetchLogBatch', start)
candidate_start = candidate_server.index('func fetchSpanBatch(')
candidate_end = candidate_server.index('// fetchLogBatch', candidate_start)
old = server[start:end]
new = candidate_server[candidate_start:candidate_end]
brace = new.index(' {') + 2
new = new[:brace] + '\n\tif !clientdb.BatchMetadataEnabled() { return fetchSpanBatchLegacy(ctx, db, since, limit, keep) }' + new[brace:]
new += old.replace('func fetchSpanBatch(', 'func fetchSpanBatchLegacy(', 1)
server = server[:start] + new + server[end:]
(base / 'batch-metadata-diagnostic-server.go').write_text(server)

debug = (base / 'snapshot-completion-debug.go').read_text()
debug = replace_once(debug, '\tm := http.NewServeMux()\n',
                     '\tm := http.NewServeMux()\n\tm.HandleFunc("/debug/batch-metadata", clientdb.BatchMetadataDiagnostic)\n')
(base / 'batch-metadata-diagnostic-debug.go').write_text(debug)

for target, replacement in [
    ('engine/clientdb/span.go', 'batch-metadata-diagnostic-span.go'),
    ('engine/clientdb/log.go', 'batch-metadata-diagnostic-log.go'),
    ('engine/clientdb/batch_metadata_legacy_log.go', 'batch-metadata-legacy-log.go'),
    ('engine/clientdb/batch_metadata_mode.go', 'batch-metadata-diagnostic-mode.go'),
    ('engine/server/telemetry.go', 'batch-metadata-diagnostic-server.go'),
    ('cmd/engine/debug.go', 'batch-metadata-diagnostic-debug.go'),
]:
    overlay['Replace'][str(engine / target)] = str(base / replacement)
(base / 'batch-metadata-engine-overlay.json').write_text(json.dumps(overlay, indent=2) + '\n')
print('PASS prepared per-batch metadata diagnostic; existing decoder and source controls preserved')
