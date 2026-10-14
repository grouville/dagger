package schema

import (
	"context"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
)

type nativeHintTestValue struct{}

func (*nativeHintTestValue) Type() *ast.Type {
	return &ast.Type{NamedType: "NativeHintTestValue", NonNull: true}
}

func TestNativeCacheHintReadsLatestPublication(t *testing.T) {
	ctx := engine.ContextWithClientMetadata(t.Context(), &engine.ClientMetadata{ClientID: "hint-schema", SessionID: "hint-schema"})
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.Close(context.Background())) })
	ctx = dagql.ContextWithCache(ctx, cache)
	server := &currentTypeDefsTestServer{}
	root := core.NewRoot(server)
	srv, err := dagql.NewServer(ctx, root)
	require.NoError(t, err)
	server.dag = srv
	ctx = core.ContextWithQuery(ctx, root)
	(&cacheSchema{}).Install(srv)
	for _, version := range []string{"v0.21.6", "v1.0.0-beta.17"} {
		schema := srv.SchemaForView(call.View(engine.APIViewVersion(version)))
		for _, field := range []string{"nativeCacheHint", "saveNativeCacheHint"} {
			require.Equal(t, version != "v0.21.6", schema.Query.Fields.ForName(field) != nil, "API visibility for %s", version)
		}
	}
	srv.InstallObject(dagql.NewClass[*nativeHintTestValue](srv))
	dagql.Fields[*core.Query]{dagql.Func("hintValue", func(context.Context, *core.Query, struct{ Name string }) (*nativeHintTestValue, error) {
		return &nativeHintTestValue{}, nil
	})}.Install(srv)

	lookup := func() dagql.Nullable[dagql.AnyID] {
		t.Helper()
		var id dagql.Nullable[dagql.AnyID]
		require.NoError(t, srv.Select(ctx, srv.Root(), &id, dagql.Selector{Field: "nativeCacheHint", Args: []dagql.NamedInput{{Name: "key", Value: dagql.NewString("project")}}}))
		return id
	}
	require.False(t, lookup().Valid)
	for _, name := range []string{"first", "second", "first"} {
		var value dagql.AnyObjectResult
		require.NoError(t, srv.Select(ctx, srv.Root(), &value, dagql.Selector{Field: "hintValue", Args: []dagql.NamedInput{{Name: "name", Value: dagql.NewString(name)}}}))
		id, err := value.ID()
		require.NoError(t, err)
		var saved dagql.Boolean
		require.NoError(t, srv.Select(ctx, srv.Root(), &saved, dagql.Selector{Field: "saveNativeCacheHint", Args: []dagql.NamedInput{
			{Name: "key", Value: dagql.NewString("project")},
			{Name: "value", Value: dagql.NewAnyID(id)},
		}}))
		require.True(t, bool(saved))
		latest := lookup()
		require.True(t, latest.Valid)
		latestID, err := latest.Value.ID()
		require.NoError(t, err)
		require.Equal(t, id.EngineResultID(), latestID.EngineResultID(), "reads and writes must not be memoized")
	}
}
