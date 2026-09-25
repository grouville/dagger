from pathlib import Path
import json
b=Path('/tmp/collections-perf/cli-boundaries');repo=Path('/home/dagger/dag');overlay={}
def save(path,source):
 p=b/path.name;p.write_text(source);overlay[str(repo/path)]=str(p)
def replace(s,a,z,n=1):
 assert s.count(a)==n,(a,s.count(a));return s.replace(a,z)
p=Path('engine/telemetry/cloud_export_sequence.go');s=(repo/p).read_text()
s=replace(s,'"net/http"','"net/http"\n "net/http/httptrace"\n "crypto/tls"\n "encoding/json"\n "os"\n "sync"')
s=replace(s,'func (t exportSequenceTransport) RoundTrip(req *http.Request) (*http.Response, error) {','''func (t exportSequenceTransport) RoundTrip(req *http.Request) (*http.Response, error) {
 id := perfNext.Add(1)
 signal := "other"
 switch req.URL.Path { case "/v1/traces": signal="traces"; case "/v1/logs": signal="logs"; case "/v1/metrics": signal="metrics" }
 report := func(event string, fields map[string]any) { if fields==nil { fields=map[string]any{} }; fields["request"]=id; fields["signal"]=signal; PerfEvent(event,fields) }
 report("http.begin",map[string]any{"bytes":req.ContentLength})
 defer func(){report("http.end",nil)}()
 trace := &httptrace.ClientTrace{
  GetConn: func(string){report("http.getConn",nil)},
  GotConn: func(i httptrace.GotConnInfo){report("http.gotConn",map[string]any{"reused":i.Reused,"idle":i.WasIdle})},
  DNSStart: func(httptrace.DNSStartInfo){report("http.dnsStart",nil)},
  DNSDone: func(i httptrace.DNSDoneInfo){report("http.dnsDone",map[string]any{"error":i.Err!=nil})},
  ConnectStart: func(string,string){report("http.connectStart",nil)},
  ConnectDone: func(_, _ string, err error){report("http.connectDone",map[string]any{"error":err!=nil})},
  TLSHandshakeStart: func(){report("http.tlsStart",nil)},
  TLSHandshakeDone: func(cs tls.ConnectionState,err error){report("http.tlsDone",map[string]any{"error":err!=nil,"protocol":cs.NegotiatedProtocol})},
  WroteRequest: func(i httptrace.WroteRequestInfo){report("http.wrote",map[string]any{"error":i.Err!=nil})},
  GotFirstResponseByte: func(){report("http.firstByte",nil)},
 }
 req=req.WithContext(httptrace.WithClientTrace(req.Context(),trace))''')
s=replace(s,'func (e *sequencedSpanExporter) ExportSpans(ctx context.Context, spans []sdktrace.ReadOnlySpan) error {','''func (e *sequencedSpanExporter) ExportSpans(ctx context.Context, spans []sdktrace.ReadOnlySpan) error {
 done:=PerfStart("export.traces");defer done()
 live:=0;for _,s:=range spans {if !s.EndTime().After(s.StartTime()){live++}}
 PerfEvent("export.batch",map[string]any{"spans":len(spans),"live":live})''')
s+='''
var perfEpoch=time.Now()
var perfMu sync.Mutex
var perfNext atomic.Uint64
func PerfEvent(event string, fields map[string]any) {
 path:=os.Getenv("DAGGER_PERF_TIMELINE");if path=="" {return}
 if fields==nil {fields=map[string]any{}}
 fields["event"]=event;fields["ms"]=float64(time.Since(perfEpoch))/float64(time.Millisecond)
 perfMu.Lock();defer perfMu.Unlock()
 f,err:=os.OpenFile(path,os.O_CREATE|os.O_APPEND|os.O_WRONLY,0600);if err!=nil{return};defer f.Close()
 _=json.NewEncoder(f).Encode(fields)
}
func PerfStart(name string) func() {
 start:=time.Now();PerfEvent("phase.begin",map[string]any{"name":name})
 return func(){PerfEvent("phase.end",map[string]any{"name":name,"duration_ms":float64(time.Since(start))/float64(time.Millisecond)})}
}
'''
save(p,s)
p=Path('internal/cmd/dagger/main.go');s=(repo/p).read_text()
s=replace(s,'PersistentPreRunE: func(cmd *cobra.Command, args []string) error {','PersistentPreRunE: func(cmd *cobra.Command, args []string) error {\n defer enginetel.PerfStart("preRun")()')
s=replace(s,'labels := enginetel.LoadDefaultLabels(workdir, engine.Version)','labelsDone:=enginetel.PerfStart("labels");labels := enginetel.LoadDefaultLabels(workdir, engine.Version);labelsDone()')
s=replace(s,'t := analytics.New(analytics.DefaultConfig(labels))','analyticsDone:=enginetel.PerfStart("analytics.init");t := analytics.New(analytics.DefaultConfig(labels));analyticsDone()')
s=replace(s,'\t\t\tt.Close()','\t\t\tdefer enginetel.PerfStart("analytics.close")();t.Close()')
s=replace(s,'func checkCloudToken(ctx context.Context, w io.Writer) error {','func checkCloudToken(ctx context.Context, w io.Writer) error {\n defer enginetel.PerfStart("token.check")()')
save(p,s)
p=Path('internal/cmd/dagger/engine.go');s=(repo/p).read_text()
s=replace(s,'sess, err := client.Connect(ctx, params)','connectDone:=enginetel.PerfStart("engine.connect");sess, err := client.Connect(ctx, params);connectDone()')
s=replace(s,'cleanup.Add("close dagger session", sess.Close)','cleanup.Add("close dagger session", func() error {defer enginetel.PerfStart("engine.close")();return sess.Close()})')
s=replace(s,'return cleanup.Run, fn(ctx, sess)','callbackDone:=enginetel.PerfStart("command");err=fn(ctx,sess);callbackDone();return cleanup.Run,err')
s=replace(s,'ctx = telemetry.Init(ctx, engineTelemetryConfig(ctx))','initDone:=enginetel.PerfStart("telemetry.init");ctx = telemetry.Init(ctx, engineTelemetryConfig(ctx));initDone()')
s=replace(s,'\t\ttelemetry.Close()','\t\tdefer enginetel.PerfStart("telemetry.close")();telemetry.Close()')
save(p,s)
(b/'overlay.json').write_text(json.dumps({'Replace':overlay},indent=2)+'\n')
