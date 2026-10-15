import json
import os
from pathlib import Path
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
tree = Path('/tmp/dagger-telemetry-batch-metadata')
decoder = Path('/tmp/dagger-telemetry-json-arrays/engine/clientdb/span.go').read_text()
decode_start = decoder.index('func UnmarshalProtoJSONs[')
decode_end = decoder.index('\nfunc MarshalProtoJSONs[')


def selected_decoder(text):
    start = text.index('func UnmarshalProtoJSONs[')
    end = text.index('\nfunc MarshalProtoJSONs[')
    text = text[:start] + decoder[decode_start:decode_end] + text[end:]
    return text.replace('import (\n', 'import (\n\t"bytes"\n', 1)


legacy = subprocess.check_output(
    ['git', 'show', '6de2877bc:engine/clientdb/span.go'], cwd=tree).decode()
legacy += '''
// Compatibility helper for the shared benchmark, using the original path.
func ReadOnlySpans(rows []Span) []sdktrace.ReadOnlySpan {
    spans := make([]sdktrace.ReadOnlySpan, 0, len(rows))
    for i := range rows { spans = append(spans, rows[i].ReadOnly()) }
    return spans
}
'''
legacy_span = base / 'batch-metadata-benchmark-span-before.go'
legacy_span.write_text(selected_decoder(legacy))
candidate_span = base / 'batch-metadata-benchmark-span-after.go'
candidate_span.write_text(selected_decoder((tree / 'engine/clientdb/span.go').read_text()))
legacy_log = base / 'batch-metadata-benchmark-log-before.go'
legacy_log.write_bytes(subprocess.check_output(
    ['git', 'show', '6de2877bc:engine/clientdb/log.go'], cwd=tree))

env = dict(os.environ, GOMAXPROCS='8')
for variant, span in [('before', legacy_span), ('after', candidate_span)]:
    replace = {str(tree / 'engine/clientdb/span.go'): str(span)}
    if variant == 'before':
        replace[str(tree / 'engine/clientdb/log.go')] = str(legacy_log)
    overlay = base / f'batch-metadata-benchmark-{variant}-overlay.json'
    overlay.write_text(json.dumps(dict(Replace=replace), indent=2) + '\n')
    command = ['/home/dagger/.local/bin/go', 'test', '-buildvcs=false',
               '-overlay=' + str(overlay), '-run=^$',
               '-bench=^Benchmark(ReadOnlySpanBatch|LogMetadataBatch)$',
               '-benchtime=500ms', '-count=5', './engine/clientdb']
    with (base / f'batch-metadata-benchmark-{variant}.log').open('w') as output:
        subprocess.run(command, cwd=tree, env=env, stdout=output,
                       stderr=subprocess.STDOUT, check=True)
    print('PASS benchmark', variant, flush=True)
