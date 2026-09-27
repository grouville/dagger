package schema

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

// A core-only schema needs neither cached TypeDef values nor module metadata.
// This also provides a work witness: the eager baseline requires EngineCache
// during Fork and cannot pass the schema-only context used here.
func TestCoreSchemaForkDoesNotRequireModuleMetadata(t *testing.T) {
	ctx := t.Context()
	server := &currentTypeDefsTestServer{}
	base, err := NewCoreSchemaBase(ctx, server)
	require.NoError(t, err)
	for _, view := range []call.View{"v0.21.5", "v1.0.0"} {
		dag, err := base.Fork(ctx, core.NewRoot(server), view)
		require.NoError(t, err)
		require.Equal(t, view, dag.View)
		schema := dag.Schema()
		require.NotNil(t, schema.Query.Fields.ForName("version"))
		require.NotNil(t, schema.Types["Container"])
		if view == "v0.21.5" {
			require.NotNil(t, schema.Query.Fields.ForName("loadContainerFromID"))
		} else {
			require.Nil(t, schema.Query.Fields.ForName("loadContainerFromID"))
		}
	}
	require.Empty(t, base.views, "schema use must not construct module TypeDef results")
}

func TestCoreSchemaForkDefersTypeDefsUntilDemand(t *testing.T) {
	testCoreSchemaTypeDefRetention(t, true)
}

// This gate also runs on the eager baseline: public metadata content and the
// actual retained TypeDef IDs are the existing contract, unlike outer IDs of
// additional wrappers synthesized by currentTypeDefs(returnAllTypes: true).
func TestCoreSchemaTypeDefContentsAfterSessionRelease(t *testing.T) {
	testCoreSchemaTypeDefRetention(t, false)
}

func testCoreSchemaTypeDefRetention(t *testing.T, requireLazy bool) {
	t.Helper()
	ctx := t.Context()
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.Close(context.Background())) })
	ctx = dagql.ContextWithCache(ctx, cache)
	ctx = engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{
		ClientID: "lazy-core-client-a", SessionID: "lazy-core-session-a",
	})
	server := &currentTypeDefsTestServer{}
	root := core.NewRoot(server)
	base, err := NewCoreSchemaBase(ctx, server)
	require.NoError(t, err)
	view := call.View("v1.0.0")
	mod := base.CoreMod(view)
	server.deps = core.NewSchemaBuilder(root, []core.Mod{mod})
	dag, err := base.Fork(ctx, root, view)
	require.NoError(t, err)
	before, err := getSchemaJSON(nil, nil, view, dag)
	require.NoError(t, err)
	if requireLazy {
		require.Empty(t, base.views)
	}

	var first dagql.ObjectResultArray[*core.TypeDef]
	err = dag.Select(ctx, dag.Root(), &first, dagql.Selector{
		Field: "currentTypeDefs", Args: []dagql.NamedInput{
			{Name: "returnAllTypes", Value: dagql.Boolean(true)},
		},
	})
	require.NoError(t, err)
	require.NotEmpty(t, first)
	require.Len(t, base.views, 1)
	firstShape := coreMetadataShape(first)
	state := base.views[view]
	require.NotNil(t, state)
	require.NotNil(t, state.objectDefsByName["Container"].Self())

	// Materializing metadata must not change the callable core schema.
	after, err := getSchemaJSON(nil, nil, view, dag)
	require.NoError(t, err)
	require.JSONEq(t, string(before), string(after))
	eagerView, err := getSchemaJSON(nil, nil, view, state.server)
	require.NoError(t, err)
	require.JSONEq(t, string(before), string(eagerView))

	// The previous engine-owned retention contract still applies when the
	// first consumer's session ends. A new session must not rebuild the view.
	require.NoError(t, cache.ReleaseSession(ctx, "lazy-core-session-a"))
	ctxB := engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{
		ClientID: "lazy-core-client-b", SessionID: "lazy-core-session-b",
	})
	dagB, err := base.Fork(ctxB, core.NewRoot(server), view)
	require.NoError(t, err)
	var second dagql.ObjectResultArray[*core.TypeDef]
	err = dagB.Select(ctxB, dagB.Root(), &second, dagql.Selector{
		Field: "currentTypeDefs", Args: []dagql.NamedInput{
			{Name: "returnAllTypes", Value: dagql.Boolean(true)},
		},
	})
	require.NoError(t, err)
	require.Equal(t, len(first), len(second))
	require.Same(t, state, base.views[view])
	require.Equal(t, firstShape, coreMetadataShape(second))
	newSessionSchema, err := getSchemaJSON(nil, nil, view, dagB)
	require.NoError(t, err)
	require.JSONEq(t, string(before), string(newSessionSchema))
	// returnAllTypes may construct additional primitive wrappers; their
	// result IDs are not retained by the core view. The actual cached core
	// TypeDefs must retain their original IDs and remain loadable.
	retained, err := mod.TypeDefs(ctxB, dagB)
	require.NoError(t, err)
	require.Equal(t, len(state.typedefs), len(retained))
	for i := range retained {
		originalID, err := state.typedefs[i].ID()
		require.NoError(t, err)
		retainedID, err := retained[i].ID()
		require.NoError(t, err)
		require.Equal(t, originalID.EngineResultID(), retainedID.EngineResultID())
		_, err = state.server.Load(ctxB, retainedID)
		require.NoError(t, err)
	}
}

func TestCoreSchemaLazyForkKeepsIndependentFields(t *testing.T) {
	ctx := t.Context()
	server := &currentTypeDefsTestServer{}
	base, err := NewCoreSchemaBase(ctx, server)
	require.NoError(t, err)
	first, err := base.Fork(ctx, core.NewRoot(server), "v1.0.0")
	require.NoError(t, err)
	second, err := base.Fork(ctx, core.NewRoot(server), "v1.0.0")
	require.NoError(t, err)
	dagql.Fields[*core.Query]{
		dagql.Func("onlyOnFirstFork", func(context.Context, *core.Query, struct{}) (dagql.String, error) {
			return "first", nil
		}),
	}.Install(first)
	require.NotNil(t, first.Schema().Query.Fields.ForName("onlyOnFirstFork"))
	require.Nil(t, second.Schema().Query.Fields.ForName("onlyOnFirstFork"))
	require.Nil(t, base.base.Schema().Query.Fields.ForName("onlyOnFirstFork"))
	require.Empty(t, base.views)
}

func TestCoreSchemaLazyForkKeepsSnapshotPreparationBoundary(t *testing.T) {
	ctx := t.Context()
	server := &currentTypeDefsTestServer{}
	base, err := NewCoreSchemaBase(ctx, server)
	require.NoError(t, err)
	marked := engine.WithSnapshotSharePreparation(ctx)
	_, err = base.Fork(marked, core.NewRoot(server), "v1.0.0")
	require.ErrorIs(t, err, engine.ErrSnapshotShareEvaluation)
	_, err = base.CoreMod("v1.0.0").TypeDefs(marked, nil)
	require.ErrorIs(t, err, engine.ErrSnapshotShareEvaluation)
	_, err = base.ForkForPersistedDecode(marked, core.NewRoot(server), "v1.0.0")
	require.NoError(t, err)
	require.Empty(t, base.views)
}

// Requests for a callable core schema may overlap the first SDK metadata
// consumer. Their schema tables and deferred metadata remain independent.
func TestCoreSchemaLazyForkDuringTypeDefDemand(t *testing.T) {
	ctx := t.Context()
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.Close(context.Background())) })
	ctx = dagql.ContextWithCache(ctx, cache)
	ctx = engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{
		ClientID: "concurrent-core-client", SessionID: "concurrent-core-session",
	})
	server := &currentTypeDefsTestServer{}
	root := core.NewRoot(server)
	base, err := NewCoreSchemaBase(ctx, server)
	require.NoError(t, err)
	const workers = 8
	errs := make(chan error, workers+1)
	start := make(chan struct{})
	var wg sync.WaitGroup
	wg.Go(func() {
		<-start
		defs, err := base.CoreMod("v1.0.0").TypeDefs(ctx, nil)
		if err == nil && len(defs) == 0 {
			err = fmt.Errorf("metadata consumer received no types")
		}
		errs <- err
	})
	for range workers {
		wg.Go(func() {
			<-start
			dag, err := base.Fork(ctx, root, "v1.0.0")
			if err == nil && dag.Schema().Query.Fields.ForName("version") == nil {
				err = fmt.Errorf("callable core schema lost version field")
			}
			errs <- err
		})
	}
	close(start)
	wg.Wait()
	close(errs)
	for err := range errs {
		require.NoError(t, err)
	}
	require.Len(t, base.views, 1)
}

// A bounded semantic projection avoids comparing opaque DagQL cache state.
// Full callable-schema content is checked separately through getSchemaJSON.
func coreMetadataShape(defs dagql.ObjectResultArray[*core.TypeDef]) map[string]string {
	out := make(map[string]string, len(defs))
	for _, result := range defs {
		def := result.Self()
		var shape strings.Builder
		fmt.Fprintf(&shape, "%s\n", coreMetadataRef(def))
		var functions dagql.ObjectResultArray[*core.Function]
		if def.AsObject.Valid {
			functions = def.AsObject.Value.Self().Functions
		} else if def.AsInterface.Valid {
			functions = def.AsInterface.Value.Self().Functions
		}
		for _, result := range functions {
			fn := result.Self()
			fmt.Fprintf(&shape, "%s:%s\n", fn.Name, coreMetadataRef(fn.ReturnType.Self()))
			for _, result := range fn.Args {
				arg := result.Self()
				fmt.Fprintf(&shape, "%s:%s default=%q path=%q address=%q ignore=%q\n",
					arg.Name, coreMetadataRef(arg.TypeDef.Self()), string(arg.DefaultValue), arg.DefaultPath, arg.DefaultAddress, arg.Ignore)
			}
		}
		out[def.Name] = shape.String()
	}
	return out
}

func coreMetadataRef(def *core.TypeDef) string {
	// Name is already the canonical reference spelling, including nested
	// list-element optionality. ToType is an SDK conversion, not a formatter,
	// and recursively constructs input decoders that this comparison needs not run.
	return fmt.Sprintf("%s:%s:optional=%t", def.Name, def.Kind, def.Optional)
}
