package core

import (
	"context"
	"sync"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func TestArtifactEvaluationSchemaScope(t *testing.T) {
	f := newModuleOwnershipTest(t)
	ctx := f.session("caller")
	f.root.Server.(*moduleObjectTestServer).defaultDeps = NewSchemaBuilder(f.root, []Mod{
		&artifactCoreForkTestMod{base: f.dag},
	}).ClientOwned()
	mod := f.module(ctx, "example", moduleOwnershipModuleOpts{})
	otherMod := f.module(ctx, "other", moduleOwnershipModuleOpts{})
	f.dag.InstallObject(dagql.NewClass(f.dag, dagql.ClassOpts[*Workspace]{}))
	workspace := func(name string) dagql.ObjectResult[*Workspace] {
		value := &Workspace{Address: name}
		call := moduleObjectTestSyntheticCall(name, value)
		detached, err := dagql.NewObjectResultForCall(value, f.dag, call)
		require.NoError(t, err)
		result, err := f.cache.GetOrInitCall(ctx, "caller", f.dag, &dagql.CallRequest{ResultCall: call}, dagql.ValueFunc(detached))
		require.NoError(t, err)
		return result.(dagql.ObjectResult[*Workspace])
	}
	firstWorkspace, otherWorkspace := workspace("first"), workspace("second")
	ctx = context.WithValue(ctx, artifactEvaluationServersKey{}, &sync.Map{})
	sharedCtx := WorkspaceToContext(ctx, firstWorkspace)

	const callers = 8
	var group sync.WaitGroup
	var servers [callers]*dagql.Server
	var errs [callers]error
	for i := range callers {
		group.Go(func() {
			servers[i], errs[i] = artifactDagqlServerForModule(sharedCtx, mod)
		})
	}
	group.Wait()
	for i := range callers {
		require.NoError(t, errs[i])
		require.Same(t, servers[0], servers[i], "one expansion shares a schema within the same scope")
	}

	for name, different := range map[string]context.Context{
		"workspace":    WorkspaceToContext(ctx, otherWorkspace),
		"no workspace": ctx,
		"client": engine.ContextWithClientMetadata(sharedCtx, &engine.ClientMetadata{
			ClientID: "other", SessionID: "caller",
		}),
		"query root":        ContextWithQuery(sharedCtx, &Query{Server: f.root.Server}),
		"another expansion": context.WithValue(sharedCtx, artifactEvaluationServersKey{}, &sync.Map{}),
	} {
		t.Run(name, func(t *testing.T) {
			server, err := artifactDagqlServerForModule(different, mod)
			require.NoError(t, err)
			require.NotSame(t, servers[0], server)
		})
	}
	other, err := artifactDagqlServerForModule(sharedCtx, otherMod)
	require.NoError(t, err)
	require.NotSame(t, servers[0], other, "different module implementations do not share a schema")
}
