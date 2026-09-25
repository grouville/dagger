from pathlib import Path
import json,difflib,shutil
b=Path('/tmp/collections-perf/cli-boundaries')
p=Path('/home/dagger/go/pkg/mod/go.opentelemetry.io/otel/sdk@v1.43.0/trace/batch_span_processor.go')
s=p.read_text();old='''\t\tcase <-bsp.timer.C:
\t\t\tif err := bsp.exportSpans(ctx); err != nil {'''
new='''\t\tcase <-bsp.timer.C:
\t\t\t// An export can outlast the timer. Include spans already queued
\t\t\t// while it was in flight instead of sending a nearly empty batch.
\t\t\t// Bound the work so producers cannot postpone an export forever.
\t\t\tbsp.batchMutex.Lock()
\t\t\tdrainReady:
\t\t\tfor i := len(bsp.batch); i < bsp.o.MaxExportBatchSize; i++ {
\t\t\t\tselect {
\t\t\t\tcase sd := <-bsp.queue:
\t\t\t\t\tif ffs, ok := sd.(forceFlushSpan); ok {
\t\t\t\t\t\tclose(ffs.flushed)
\t\t\t\t\t\tcontinue
\t\t\t\t\t}
\t\t\t\t\tbsp.batch = append(bsp.batch, sd)
\t\t\t\tdefault:
\t\t\t\t\tbreak drainReady
\t\t\t\t}
\t\t\t}
\t\t\tbsp.batchMutex.Unlock()
\t\t\tif err := bsp.exportSpans(ctx); err != nil {'''
assert s.count(old)==1;s=s.replace(old,new)
a=b/'batch_span_processor.go';a.write_text(s)
# Go forbids overlays inside GOMODCACHE. Copy the SDK and replace the module.
sdk=b/'otel-sdk';shutil.copytree(p.parent.parent,sdk,dirs_exist_ok=True)
for f in sdk.rglob('*'):
 if f.is_file():f.chmod(0o644)
(sdk/'trace/batch_span_processor.go').write_text(s)
repo=Path('/home/dagger/dag')
(b/'batch.mod').write_text((repo/'go.mod').read_text()+f'\nreplace go.opentelemetry.io/otel/sdk => {sdk}\n')
shutil.copyfile(repo/'go.sum',b/'batch.sum')
(b/'otel-batch-prototype.patch').write_text(''.join(difflib.unified_diff(p.read_text().splitlines(True),s.splitlines(True),fromfile='a/trace/batch_span_processor.go',tofile='b/trace/batch_span_processor.go')))
