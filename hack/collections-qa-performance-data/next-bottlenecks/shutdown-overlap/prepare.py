from pathlib import Path
import json,subprocess
repo=Path('/home/dagger/dag'); b=Path('/tmp/collections-perf/shutdown-overlap')
overlay=json.loads(Path('/tmp/collections-perf/post-rebase-io/complete-overlay.json').read_text())
def save(rel,s):
 p=b/rel.replace('/','_');p.write_text(s);subprocess.run(['gofmt','-w',str(p)],check=True);overlay['Replace'][str(repo/rel)]=str(p)
s=(repo/'engine/client/client.go').read_text().replace('"net/http"','"net/http"\n"net/http/httptrace"\n"net/textproto"')
s=s.replace('func (c *Client) Close() (rerr error) {','''func (c *Client) Close() error { return c.close(nil) }

// CloseWithTelemetryDrain permits a caller to finalize its own telemetry after
// the engine streams have drained, while the engine still exports to Cloud.
// It retains all connections until the final shutdown response. Older engines
// do not send the checkpoint; the caller must finalize in its normal cleanup.
func (c *Client) CloseWithTelemetryDrain(drained func()) error { return c.close(drained) }

func (c *Client) close(onTelemetryDrained func()) (rerr error) {''')
start=s.index('\tshutdownErr := c.shutdownServer()');end=s.index('\n\tc.closeMu.Lock()',start)
s=s[:start]+'''\tvar shutdownErr error
\tdidDrain := false
\tif onTelemetryDrained == nil || c.telemetry == nil {
\t\tshutdownErr = c.shutdownServer(nil)
\t} else {
\t\tready := make(chan struct{}, 1)
\t\tdone := make(chan error, 1)
\t\tgo func() { done <- c.shutdownServer(func() { select { case ready <- struct{}{}: default: } }) }()
\t\tselect {
\t\tcase shutdownErr = <-done:
\t\tcase <-ready:
\t\t\tdidDrain = c.drainTelemetry()
\t\t\tif didDrain { onTelemetryDrained() }
\t\t\tshutdownErr = <-done
\t\t}
\t}
\tif shutdownErr != nil {
\t\trerr = errors.Join(rerr, fmt.Errorf("shutdown: %w", shutdownErr))
\t} else if c.telemetry != nil && !didDrain {
\t\tc.drainTelemetry()
\t}
''' + s[end:]
idx=s.index('\ntype otlpConsumer struct')
s=s[:idx]+'''
// drainTelemetry keeps receivers alive until every stream reaches its terminal
// frame. A transport failure is diagnostic, not the command's exit status.
func (c *Client) drainTelemetry() bool {
 ctx, cancel := context.WithTimeout(context.WithoutCancel(c.internalCtx), clientShutdownTimeout())
 defer cancel()
 drained := make(chan error, 1)
 go func() { drained <- c.telemetry.Wait() }()
 select {
 case err := <-drained:
  if err != nil { slog.Warn("telemetry drain failed after shutdown", "err", err); return false }
  return true
 case <-ctx.Done():
  slog.Warn("telemetry drain timed out after shutdown", "timeout", clientShutdownTimeout())
  return false
 }
}
''' +s[idx:]
s=s.replace('func (c *Client) shutdownServer() error {','func (c *Client) shutdownServer(localTelemetryFlushed func()) error {')
pos=s.index('func (c *Client) shutdownServer(');at=s.index('\n\treq.SetBasicAuth',pos)
s=s[:at]+'''
 if localTelemetryFlushed != nil {
  req.Header.Set("X-Dagger-Shutdown-Phase", "local-telemetry-flushed")
  req = req.WithContext(httptrace.WithClientTrace(req.Context(), &httptrace.ClientTrace{
   Got1xxResponse: func(code int, header textproto.MIMEHeader) error {
    if code == http.StatusEarlyHints && header.Get("X-Dagger-Shutdown-Phase") == "local-telemetry-flushed" { localTelemetryFlushed() }
    return nil
   },
  }))
 }
''' +s[at:]
save('engine/client/client.go',s)
s=(repo/'engine/server/session.go').read_text();start=s.index('func (srv *Server) serveShutdown(');end=s.index('// Stitch in',start);piece=s[start:end]
idx=piece.index('\n\tif client.clientID == sess.mainClientCallerID {')
piece=piece[:idx]+'''
 // Experimental opt-in checkpoint. Keep credentials/attachables usable until
 // Cloud has drained, but finish services and local telemetry first.
 overlap := client.clientID == sess.mainClientCallerID && sess.publishesToCloud() &&
  r.Header.Get("X-Dagger-Shutdown-Phase") == "local-telemetry-flushed"
 flushLocal := sync.OnceFunc(func() {
  flushErr := drainPhase("flush session telemetry", func() error {
   return sess.FlushTelemetry(ctx, "client shutdown")
  })
  if flushErr != nil {
   slog.Error("failed to flush telemetry", "error", flushErr)
   shutdownErr = errors.Join(shutdownErr, fmt.Errorf("flush telemetry: %w", flushErr))
  }
  client.closeShutdownOnce.Do(func() { close(client.shutdownCh) })
 })
 stopServices := sync.OnceFunc(func() {
  _ = drainPhase("stop session services", func() error {
   sess.services.StopSessionServices(ctx, sess.sessionID)
   return nil
  })
 })
''' +piece[idx:]
idx=piece.index('\n\t\t// Publish what the session')
piece=piece[:idx]+'''
  if overlap {
   stopServices()
   flushLocal()
   if shutdownErr == nil {
    w.Header().Set("X-Dagger-Shutdown-Phase", "local-telemetry-flushed")
    w.WriteHeader(http.StatusEarlyHints)
    w.Header().Del("X-Dagger-Shutdown-Phase")
   }
  }
''' +piece[idx:]
a=piece.index('\n\t\t// Stop services,');z=piece.index('\n\t\tdefer func()',a);piece=piece[:a]+'\n\t\tstopServices()\n'+piece[z:]
a=piece.index('\n\t// Trace/log providers');z=piece.index('\n\treturn shutdownErr',a);piece=piece[:a]+'\n\tflushLocal()\n'+piece[z:]
s=s[:start]+piece+s[end:];save('engine/server/session.go',s)
s=(repo/'internal/cmd/dagger/engine.go').read_text().replace('"os"','"os"\n"sync"')
s=s.replace('ctx, cleanupTelemetry := initEngineTelemetry(ctx)','ctx, finishTelemetry, cleanupTelemetry := initEngineTelemetryPhased(ctx)',1)
s=s.replace('cleanup.Add("close dagger session", sess.Close)','cleanup.Add("close dagger session", func() error {\nreturn sess.CloseWithTelemetryDrain(func() { finishTelemetry(rerr) })\n})',1)
a=s.index('func initEngineTelemetry(ctx context.Context)');s=s[:a]+'''func initEngineTelemetry(ctx context.Context) (context.Context, func(error)) {
 ctx, _, close := initEngineTelemetryPhased(ctx)
 return ctx, close
}

func initEngineTelemetryPhased(ctx context.Context) (context.Context, func(error), func(error)) {''' +s[a+len('func initEngineTelemetry(ctx context.Context) (context.Context, func(error)) {'):]
a=s.index('\n\treturn ctx, func(rerr error) {',s.index('func initEngineTelemetryPhased'))
s=s[:a]+s[a:].replace('return ctx, func(rerr error) {','var finishOnce sync.Once\nfinish := func(rerr error) { finishOnce.Do(func() {',1).replace('\n\t\ttelemetry.Close()','\n})\n}\nreturn ctx, finish, func(rerr error) {\nfinish(rerr)\n\t\ttelemetry.Close()',1)
save('internal/cmd/dagger/engine.go',s)
(b/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
