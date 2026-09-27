from pathlib import Path
D=Path(__file__).resolve().parent
S=Path('/home/dagger/dag/engine/server/session_workspaces.go')
s=S.read_text();(D/'session_workspaces.baseline.go').write_text(s)
s=s.replace('''	jobs := parallel.New().
		WithContextualTracer(true).
		WithLimit(moduleLoadParallelism(len(loads)))
''','''	// Bound each phase independently. Source resolution can itself load SDKs,
	// so this is bounded pipelining, not an I/O-only concurrency allowance.
	pipeline := newModuleLoadPipeline(len(loads))
	jobs := pipeline.jobs()
''',1)
s=s.replace('''			resolved, err := srv.resolveModuleLoad(ctx, client.dag, load)
''','''			src, err := runModuleLoadStage(ctx, pipeline.sources, func(ctx context.Context) (dagql.ObjectResult[*core.ModuleSource], error) {
				return srv.resolveModuleSource(ctx, client.dag, load.mod)
			})
			if err != nil {
				resolveErrs[i] = err
				return nil //nolint:nilerr // errors collected for deterministic ordering
			}
			resolved, err := runModuleLoadStage(ctx, pipeline.modules, func(ctx context.Context) (resolvedModuleLoad, error) {
				return srv.resolveModuleLoad(ctx, client.dag, load, src)
			})
''',1)
s=s.replace('''	load moduleLoadRequest,
) (resolvedModuleLoad, error) {
	primary, err := srv.resolveModule(ctx, dag, load.mod)
''','''	load moduleLoadRequest,
	primarySrc dagql.ObjectResult[*core.ModuleSource],
) (resolvedModuleLoad, error) {
	primary, err := srv.resolveModuleSourceAsModule(ctx, dag, primarySrc, load.mod)
''',1)
start=s.index('// resolveModule resolves a module through the dagql pipeline.')
end=s.index('// pendingRelatedModule adapts',start)
part=s[start:end]
part=part.replace('// resolveModule resolves a module through the dagql pipeline.','// resolveModuleSource resolves and validates a module source through the dagql pipeline.')
part=part.replace('func (srv *Server) resolveModule(', 'func (srv *Server) resolveModuleSource(')
part=part.replace('dagql.ObjectResult[*core.Module]', 'dagql.ObjectResult[*core.ModuleSource]')
part=part.replace('return srv.resolveModuleSourceAsModule(ctx, dag, src, mod)', 'return src, nil')
s=s[:start]+part+s[end:]
s=s.replace('\t"github.com/dagger/dagger/util/parallel"\n', '')
assert 'func (srv *Server) resolveModule(' not in s
assert s.count('newModuleLoadPipeline(len(loads))')==1
assert s.count('return srv.resolveModuleLoad(ctx, client.dag, load, src)')==1
(D/'session_workspaces.go').write_text(s)
