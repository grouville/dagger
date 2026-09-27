from pathlib import Path
import json,hashlib,subprocess,difflib
ROOT=Path('/home/dagger/dag')
OUT=Path('/tmp/collections-perf/cli-exit-tail-v2')
OTEL=Path('/tmp/collections-perf/cli-exit-tail-v2/otel-go-pinned')
replacements={};manifest=[];patch=[]
def replace(s,a,b,n=1):
 assert s.count(a)==n,(a,s.count(a),n)
 return s.replace(a,b)
def save(original,label,s):
 dest=OUT/'source'/label
 dest.write_text(s)
 base=original.read_text() if original.exists() else ''
 replacements[str(original)]=str(dest)
 manifest.append({'original':str(original),'overlay':str(dest),'baseSHA256':hashlib.sha256(base.encode()).hexdigest() if base else None,'candidateSHA256':hashlib.sha256(s.encode()).hexdigest()})
 patch.extend(difflib.unified_diff(base.splitlines(True),s.splitlines(True),fromfile=str(original),tofile=str(dest)))

p=ROOT/'internal/cmd/dagger/main.go';s=p.read_text()
s=replace(s,'func Main() {','func Main() {\n mainDone:=telemetry.PerfExitStart("cli.main");defer func(){mainDone();telemetry.PerfExitFlush()}()')
s=replace(s,'exitWithCode := func(code int) {\n\t\tstop()','exitWithCode := func(code int) {\n\t\tstop();mainDone();telemetry.PerfExitFlush()')
s=replace(s,'PersistentPreRunE: func(cmd *cobra.Command, args []string) error {','PersistentPreRunE: func(cmd *cobra.Command, args []string) error {\n defer telemetry.PerfExitStart("cli.pre_run")()')
s=replace(s,'labels := enginetel.LoadDefaultLabels(workdir, engine.Version)','labelsDone:=telemetry.PerfExitStart("cli.labels");labels := enginetel.LoadDefaultLabels(workdir, engine.Version);labelsDone()')
s=replace(s,'\t\t\tt.Close()','\t\t\tdefer telemetry.PerfExitStart("analytics.finalize")();t.Close()')
s=replace(s,'cobra.OnFinalize(startOAuthTokenRefresher(cmd.Context()))','stopOAuth:=startOAuthTokenRefresher(cmd.Context());cobra.OnFinalize(func(){defer telemetry.PerfExitStart("oauth.finalize")();stopOAuth()})')
s=replace(s,'if err := rootCmd.ExecuteContext(ctx); err != nil {','executeDone:=telemetry.PerfExitStart("cli.execute");executeErr:=rootCmd.ExecuteContext(ctx);executeDone();if err:=executeErr; err != nil {')
save(p,'cli_main.go',s)

p=ROOT/'internal/cmd/dagger/engine.go';s=p.read_text()
s=replace(s,') (rerr error) {',') (rerr error) {\n defer telemetry.PerfExitStart("cli.with_engine_frontend")()',2)
s=replace(s,'sess, err := client.Connect(ctx, params)','connectDone:=telemetry.PerfExitStart("engine.connect");sess, err := client.Connect(ctx, params);connectDone()')
s=replace(s,'sess, err := client.Connect(ctx, fp)','connectDone:=telemetry.PerfExitStart("engine.connect");sess, err := client.Connect(ctx, fp);connectDone()')
s=replace(s,'return cleanup.Run, fn(ctx, sess)','commandDone:=telemetry.PerfExitStart("cli.command");commandErr:=fn(ctx,sess);commandDone();return cleanup.Run,commandErr')
s=replace(s,'return cleanup.Run, fn(ctx, connect)','commandDone:=telemetry.PerfExitStart("cli.command");commandErr:=fn(ctx,connect);commandDone();return cleanup.Run,commandErr')
s=replace(s,'\t\tstdio.Close()\n\t\ttelemetry.EndWithCause(span, &rerr)\n\t\ttelemetry.Close()','\t\tstdioDone:=telemetry.PerfExitStart("cli.stdio_close");stdio.Close();stdioDone()\n\t\trootDone:=telemetry.PerfExitStart("cli.root_end");telemetry.EndWithCause(span, &rerr);rootDone()\n\t\tcloseDone:=telemetry.PerfExitStart("cli.telemetry_close");telemetry.Close();closeDone()')
save(p,'cli_engine.go',s)

p=ROOT/'engine/client/client.go';s=p.read_text()
s=replace(s,'func (c *Client) Close() (rerr error) {','func (c *Client) Close() (rerr error) {\n defer telemetry.PerfExitStart("engine.close")()')
s=replace(s,'shutdownErr := c.shutdownServer()','shutdownDone:=telemetry.PerfExitStart("engine.shutdown_http");shutdownErr := c.shutdownServer();shutdownDone()')
s=replace(s,'\t\tdrained := make(chan error, 1)','\t\tdrainDone:=telemetry.PerfExitStart("engine.subscribers_drain");drained := make(chan error, 1)')
s=replace(s,'\t\tcancel()\n\t}\n\n\tc.closeMu.Lock()','\t\tcancel();drainDone()\n\t}\n\n\tlockDone:=telemetry.PerfExitStart("engine.close_lock");c.closeMu.Lock();lockDone()')
s=replace(s,'\tif err := c.eg.Wait(); err != nil {','\tcleanupDone:=telemetry.PerfExitStart("engine.clients_cleanup");cleanupErr:=c.eg.Wait();cleanupDone();if err:=cleanupErr; err != nil {')
s=replace(s,'\t\tif err := c.telemetry.Wait(); err != nil {','\t\tfinalDrainDone:=telemetry.PerfExitStart("engine.subscribers_final_drain");finalDrainErr:=c.telemetry.Wait();finalDrainDone();if err:=finalDrainErr; err != nil {')
start=s.index('func (c *Client) shutdownServer() error {');end=s.index('\nfunc ',start+1)
f=s[start:end]
f=replace(f,'\tresp, err := c.httpClient.Do(req)','\treq, observe:=telemetry.PerfExitHTTP(req,"engine.shutdown_request");resp, err := c.httpClient.Do(req);resp=observe(resp,err)')
s=s[:start]+f+s[end:]
save(p,'engine_client.go',s)

p=ROOT/'engine/telemetry/cloud_export_sequence.go';s=p.read_text()
s=replace(s,'"github.com/google/uuid"','"github.com/google/uuid"\n telemetry "github.com/dagger/otel-go"')
s=replace(s,'func (t exportSequenceTransport) RoundTrip(req *http.Request) (*http.Response, error) {','''func (t exportSequenceTransport) RoundTrip(req *http.Request) (resp *http.Response, rerr error) {
 kind:="cloud.other";switch req.URL.Path {case "/v1/traces":kind="cloud.traces";case "/v1/logs":kind="cloud.logs";case "/v1/metrics":kind="cloud.metrics"}
 req, observe:=telemetry.PerfExitHTTP(req,kind);defer func(){resp=observe(resp,rerr)}()''')
s=replace(s,'func (e *sequencedSpanExporter) ExportSpans(ctx context.Context, spans []sdktrace.ReadOnlySpan) error {','func (e *sequencedSpanExporter) ExportSpans(ctx context.Context, spans []sdktrace.ReadOnlySpan) error {\n defer telemetry.PerfExitStartValues("cloud.export.traces",map[string]int64{"records":int64(len(spans))})()')
s=replace(s,'func (e *sequencedLogExporter) Export(ctx context.Context, logs []sdklog.Record) error {','func (e *sequencedLogExporter) Export(ctx context.Context, logs []sdklog.Record) error {\n defer telemetry.PerfExitStartValues("cloud.export.logs",map[string]int64{"records":int64(len(logs))})()')
save(p,'cloud_export_sequence.go',s)

p=ROOT/'analytics/analytics.go';s=p.read_text()
s=replace(s,'"github.com/dagger/dagger/engine"','"github.com/dagger/dagger/engine"\n oteldiag "github.com/dagger/otel-go"')
s=replace(s,'\tresp, err := http.DefaultClient.Do(req)','\treq,observe:=oteldiag.PerfExitHTTP(req,"analytics.http");resp, err := http.DefaultClient.Do(req);resp=observe(resp,err)')
save(p,'analytics.go',s)

p=OTEL/'init.go';s=p.read_text()
for provider,kind in [('tracerProvider','traces'),('loggerProvider','logs'),('meterProvider','metrics')]:
 s=replace(s,f'if err := {provider}.Shutdown(flushCtx); err != nil {{',f'done:=PerfExitStart("otel.provider.{kind}");err:={provider}.Shutdown(flushCtx);done();if err != nil {{')
save(p,'otel_init.go',s)

p=OTEL/'perf_exit_diagnostic.go';dest=OUT/'source/perf_exit_diagnostic.go'
replacements[str(p)]=str(dest)
manifest.append({'original':str(p),'overlay':str(dest),'baseSHA256':None,'candidateSHA256':hashlib.sha256(dest.read_bytes()).hexdigest()})
(OUT/'overlay.json').write_text(json.dumps({'Replace':replacements},indent=2)+'\n')
(OUT/'source-manifest.json').write_text(json.dumps({'baseCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'files':manifest,'status':'prepared; not built or executed'},indent=2)+'\n')
(OUT/'diagnostic.patch').write_text(''.join(patch))
