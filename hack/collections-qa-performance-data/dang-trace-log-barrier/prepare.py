from pathlib import Path
import difflib, hashlib, json, subprocess
ROOT=Path('/home/dagger/dag')
LAB=Path(__file__).resolve().parent
FILES=('engine/server/session.go','core/query.go','core/sdk/dang/v2/helpers.go','core/schema/test_server_test.go','core/telemetry_test.go')
sha=lambda x:hashlib.sha256(x).hexdigest()
base={p:(ROOT/p).read_text() for p in FILES}
candidate=dict(base)
s=base['engine/server/session.go']
s=s.replace('return client.meterProvider.ForceFlush(ctx)', '''flushCtx, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "telemetry.flushClientMetrics", wcprof.OpOpts{})
	err := client.meterProvider.ForceFlush(flushCtx)
	op.EndErr(err)
	return err''', 1)
old='''	if sess.tracerProvider != nil {
		traceDur = timedProviderOp(ctx, &errs, sess.tracerProvider.ForceFlush)
	}
	if sess.loggerProvider != nil {
		logDur = timedProviderOp(ctx, &errs, sess.loggerProvider.ForceFlush)
	}
	metricStart := time.Now()
	errs = errors.Join(errs, runClientMetricOp(ctx, clients, "flush metrics", (*clientRuntime).flushMetrics))
	metricDur = time.Since(metricStart)'''
new='''	if sess.tracerProvider != nil {
		traceDur = timedTelemetryFlush(ctx, &errs, "telemetry.flushTraces", sess.tracerProvider.ForceFlush)
	}
	if sess.loggerProvider != nil {
		logDur = timedTelemetryFlush(ctx, &errs, "telemetry.flushLogs", sess.loggerProvider.ForceFlush)
	}
	metricDur = timedTelemetryFlush(ctx, &errs, "telemetry.flushMetrics", func(ctx context.Context) error {
		return runClientMetricOp(ctx, clients, "flush metrics", (*clientRuntime).flushMetrics)
	})'''
assert s.count(old)==1
s=s.replace(old,new)
helper='''// timedTelemetryFlush adds fixed phase names only when wall-clock profiling is
// enabled. The client-metric child phase starts after metricMu is held, so its
// count is the number of actual provider ForceFlush calls, not retained records.
func timedTelemetryFlush(ctx context.Context, errs *error, phase string, flush func(context.Context) error) time.Duration {
	flushCtx, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, phase, wcprof.OpOpts{})
	start := time.Now()
	err := flush(flushCtx)
	op.EndErr(err)
	*errs = errors.Join(*errs, err)
	return time.Since(start)
}

'''
s=s.replace('func (sess *daggerSession) clientMetricRuntimes()',helper+'func (sess *daggerSession) clientMetricRuntimes()',1)
profile=s
old='func (sess *daggerSession) FlushTelemetry(ctx context.Context, reason string) error {'
new='''func (sess *daggerSession) FlushTelemetry(ctx context.Context, reason string) error {
	return sess.flushTelemetry(ctx, reason, true)
}

// FlushTraceLogs makes the entire session's trace/log queues locally visible.
// It does not collect metrics: periodic readers and runtime/session shutdown
// retain ownership of those collections. Unlike a client-subtree flush, this
// preserves telemetry from every origin, including detached/nested work.
func (sess *daggerSession) FlushTraceLogs(ctx context.Context, reason string) error {
	return sess.flushTelemetry(ctx, reason, false)
}

func (sess *daggerSession) flushTelemetry(ctx context.Context, reason string, includeMetrics bool) error {'''
assert s.count(old)==1
s=s.replace(old,new)
old='''	clients := sess.clientMetricRuntimes()
	sess.clientMu.RLock()
	records := len(sess.clientRecords)'''
new='''	var clients []*clientRuntime
	if includeMetrics {
		clients = sess.clientMetricRuntimes()
	}
	sess.clientMu.RLock()
	records := len(sess.clientRecords)'''
assert s.count(old)==1
s=s.replace(old,new)
old='''	metricDur = timedTelemetryFlush(ctx, &errs, "telemetry.flushMetrics", func(ctx context.Context) error {
		return runClientMetricOp(ctx, clients, "flush metrics", (*clientRuntime).flushMetrics)
	})'''
new='''	if includeMetrics {
		metricDur = timedTelemetryFlush(ctx, &errs, "telemetry.flushMetrics", func(ctx context.Context) error {
			return runClientMetricOp(ctx, clients, "flush metrics", (*clientRuntime).flushMetrics)
		})
	}'''
assert s.count(old)==1
s=s.replace(old,new)
needle='func (srv *Server) ClientTelemetry(ctx context.Context, sessID, clientID string) (*clientdb.DB, error) {'
method='''// FlushSessionTraceLogs is the local visibility barrier used by in-engine
// calls. It preserves session-wide origin routing without sampling every live
// client's metrics at each call boundary.
func (srv *Server) FlushSessionTraceLogs(ctx context.Context) error {
	record, err := srv.clientRecordFromContext(ctx)
	if err != nil {
		return err
	}
	return record.daggerSession.FlushTraceLogs(ctx, "FlushSessionTraceLogs API")
}

'''
assert needle in s
candidate['engine/server/session.go']=s.replace(needle,method+needle,1)
p='core/query.go'
needle='\tFlushSessionTelemetry(ctx context.Context) error\n'
assert needle in candidate[p]
candidate[p]=candidate[p].replace(needle,needle+'''
	// Make all session spans and logs locally visible without collecting metrics.
	// Periodic metric collection and runtime/session shutdown remain independent.
	FlushSessionTraceLogs(ctx context.Context) error
''',1)
p='core/sdk/dang/v2/helpers.go'
assert candidate[p].count('query.Server.FlushSessionTelemetry(flushCtx)')==1
candidate[p]=candidate[p].replace('query.Server.FlushSessionTelemetry(flushCtx)','query.Server.FlushSessionTraceLogs(flushCtx)',1)
p='core/schema/test_server_test.go'
needle='func (s *currentTypeDefsTestServer) FlushSessionTelemetry(context.Context) error {\n\treturn nil\n}\n'
assert needle in candidate[p]
candidate[p]=candidate[p].replace(needle,needle+'\nfunc (s *currentTypeDefsTestServer) FlushSessionTraceLogs(context.Context) error {\n\treturn nil\n}\n',1)
p='core/telemetry_test.go'
needle='func (ms *mockServer) FlushSessionTelemetry(context.Context) error     { return nil }\n'
assert needle in candidate[p]
candidate[p]=candidate[p].replace(needle,needle+'func (ms *mockServer) FlushSessionTraceLogs(context.Context) error     { return nil }\n',1)
for kind, sources in [('base',base),('source',candidate),('profile-only',{'engine/server/session.go':profile})]:
    for p,data in sources.items():
        out=LAB/kind/p
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(data)
        subprocess.run(['gofmt','-w',str(out)],check=True)
# A fail-first witness uses the candidate API but deliberately restores full
# collection at the new completion barrier; it must fail the metric-zero test.
negative=(LAB/'source/engine/server/session.go').read_text().replace('return sess.flushTelemetry(ctx, reason, false)','return sess.flushTelemetry(ctx, reason, true)',1)
(LAB/'negative').mkdir(exist_ok=True)
(LAB/'negative/session.go').write_text(negative)
patch=''
for p in FILES:
    patch+=''.join(difflib.unified_diff((ROOT/p).read_text().splitlines(True),(LAB/'source'/p).read_text().splitlines(True),fromfile='a/'+p,tofile='b/'+p))
(LAB/'prototype.patch').write_text(patch)
(LAB/'source-overlay.json').write_text(json.dumps({'Replace':{str(ROOT/p):str(LAB/'source'/p) for p in FILES if not p.endswith('_test.go')}},indent=2)+'\n')
(LAB/'profile-overlay.json').write_text(json.dumps({'Replace':{str(ROOT/'engine/server/session.go'):str(LAB/'profile-only/engine/server/session.go')}},indent=2)+'\n')
(LAB/'test-overlay.json').write_text(json.dumps({'Replace':{str(ROOT/p):str(LAB/'source'/p) for p in FILES}},indent=2)+'\n')
(LAB/'manifest.json').write_text(json.dumps({'status':'prepared source only; no compilation, tests or runtime', 'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'base_sha256':{p:sha((ROOT/p).read_bytes()) for p in FILES},'files':{str(p.relative_to(LAB)):sha(p.read_bytes()) for p in LAB.rglob('*') if p.is_file() and p.name!='manifest.json'}},indent=2)+'\n')
