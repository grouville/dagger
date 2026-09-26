from pathlib import Path
import json,difflib
root=Path('/home/dagger/dag');out=Path('/tmp/collections-perf/sdk-edit-audit/cloud-coalescing')
p=root/'engine/telemetry/callpayloadbatch.go';s=p.read_text()
s=s.replace('maxExportBatchSize int','maxExportBatchSize int\n\texportDelay time.Duration',1)
anchor='func NewCallPayloadBatchProcessor('
option='''// WithCallPayloadExportDelay controls the window for coalescing a payload burst.
// Nonpositive values retain the default. Explicit flush/shutdown and retry
// backoff keep their existing behavior.
func WithCallPayloadExportDelay(delay time.Duration) CallPayloadBatchOption {
    return func(processor *CallPayloadBatchProcessor) {
        if delay > 0 { processor.exportDelay = delay }
    }
}

'''
s=s.replace(anchor,option+anchor,1)
s=s.replace('maxExportBatchSize: LogExportMaxBatchSize,','maxExportBatchSize: LogExportMaxBatchSize,\n\t\texportDelay: CallPayloadExportDelay,',1)
assert s.count('arm(CallPayloadExportDelay)')==2
s=s.replace('arm(CallPayloadExportDelay)','arm(processor.exportDelay)')
(out/'callpayloadbatch.go').write_text(s)
p=root/'engine/server/session_cloud_telemetry.go';s=p.read_text();needle='enginetel.WithCallPayloadExportMaxBatchSize(512))';assert s.count(needle)==1
s=s.replace(needle,'enginetel.WithCallPayloadExportMaxBatchSize(512),\n\t\t\tenginetel.WithCallPayloadExportDelay(telemetry.NearlyImmediate))',1)
(out/'session_cloud_telemetry.go').write_text(s)
repl={'engine/telemetry/callpayloadbatch.go':'callpayloadbatch.go','engine/server/session_cloud_telemetry.go':'session_cloud_telemetry.go','engine/telemetry/callpayloadcoalescing_test.go':'callpayloadcoalescing_test.go'}
(out/'overlay.json').write_text(json.dumps({'Replace':{str(root/rel):str(out/src) for rel,src in repl.items()}},indent=2)+'\n')
