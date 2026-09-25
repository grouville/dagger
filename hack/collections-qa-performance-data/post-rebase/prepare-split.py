from pathlib import Path
import json
b=Path('/tmp/collections-perf/post-rebase-io');root=Path('/home/dagger/dag');ov=json.loads((b/'complete-overlay.json').read_text())
p=root/'engine/telemetry/cloud_exporters.go';s=p.read_text().replace('"fmt"','"fmt"\n"errors"')
needle='\tmetricExporter, err := otlpmetrichttp.New(ctx,'
assert s.count(needle)==1
s=s.replace(needle,'''    payloadSequencer := newExportSequencer()
    payloadExporter, err := otlploghttp.New(ctx,
        otlploghttp.WithEndpointURL(cloudEndpoint.JoinPath("v1", "logs").String()),
        otlploghttp.WithHeaders(headers),
        otlploghttp.WithHTTPClient(httpClient(payloadSequencer)))
    if err != nil { return nil, nil, nil, fmt.Errorf("configure cloud call payloads: %w", err) }
'''+needle)
s=s.replace('&sequencedLogExporter{sequencer: logSequencer, exporter: logExporter},','''&splitCloudLogExporter{
        Exporter: &sequencedLogExporter{sequencer: logSequencer, exporter: logExporter},
        payload: &sequencedLogExporter{sequencer: payloadSequencer, exporter: payloadExporter},
    },''')
s+='''
// Prototype: independent writers share credentials/transport, not Export calls.
type splitCloudLogExporter struct {
    sdklog.Exporter
    payload sdklog.Exporter
}
func (e *splitCloudLogExporter) PayloadExporter() sdklog.Exporter { return e.payload }
func (e *splitCloudLogExporter) Shutdown(ctx context.Context) error {
    return errors.Join(e.payload.Shutdown(ctx), e.Exporter.Shutdown(ctx))
}
'''
p2=b/'split-cloud-exporters.go';p2.write_text(s);ov['Replace'][str(p)]=str(p2)
p=root/'engine/server/session_cloud_telemetry.go';s=p.read_text()
s=s.replace('''	exporter = newSerialLogExporter(exporter)
	records := sdklog.NewBatchProcessor''','''    var payloadExporter sdklog.Exporter
    if split, ok := exporter.(interface { PayloadExporter() sdklog.Exporter }); ok {
        payloadExporter = split.PayloadExporter()
    } else {
        exporter = newSerialLogExporter(exporter)
        payloadExporter = exporter
    }
    records := sdklog.NewBatchProcessor''')
s=s.replace('payloads: enginetel.NewCallPayloadBatchProcessor(exporter,','payloads: enginetel.NewCallPayloadBatchProcessor(payloadExporter,')
p2=b/'split-session-cloud.go';p2.write_text(s);ov['Replace'][str(p)]=str(p2)
(b/'split-overlay.json').write_text(json.dumps(ov,indent=2)+'\n')
