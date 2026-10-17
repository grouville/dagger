package schema

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func dimensionKeyFieldsFixture(t testing.TB, count int, direct bool) (context.Context, *dagql.Server) {
	t.Helper()
	ctx := engine.ContextWithClientMetadata(t.Context(), &engine.ClientMetadata{ClientID: "keys", SessionID: "keys"})
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.CloseDiscardingPersistence()) })
	ctx = dagql.ContextWithCache(ctx, cache)
	query := &core.Query{}
	ctx = core.ContextWithQuery(ctx, query)
	srv, err := dagql.NewServer(ctx, query)
	require.NoError(t, err)
	dagql.Fields[*core.ArtifactDimensionKey]{}.Install(srv)
	class := srv.InstallObject(dagql.NewClass[*core.ArtifactDimensionKey](srv)).(dagql.Class[*core.ArtifactDimensionKey])
	for _, name := range []string{"dimension", "key"} {
		field, ok := class.Field(name, "")
		require.True(t, ok)
		field.Spec.DoNotCache = ""
		if direct {
			field.Spec.DoNotCache = "simple field selection"
		}
	}
	dagql.Fields[*core.Query]{
		dagql.Func("keys", func(_ context.Context, _ *core.Query, args struct{ Generation int }) ([]*core.ArtifactDimensionKey, error) {
			keys := make([]*core.ArtifactDimensionKey, count)
			for i := range keys {
				keys[i] = &core.ArtifactDimensionKey{Dimension: "rust/packages", Key: fmt.Sprintf("crate-%d-%d", args.Generation, i)}
			}
			return keys, nil
		}),
	}.Install(srv)
	return ctx, srv
}

func TestDimensionKeyFieldsThroughObjectIDs(t *testing.T) {
	for _, direct := range []bool{false, true} {
		t.Run(fmt.Sprint(direct), func(t *testing.T) {
			ctx, srv := dimensionKeyFieldsFixture(t, 3, direct)
			for generation := range 2 {
				result, err := srv.Query(ctx, `query($generation: Int!) { keys(generation: $generation) { id dimension key } }`, map[string]any{"generation": generation})
				require.NoError(t, err)
				encoded, err := json.Marshal(result)
				require.NoError(t, err)
				require.NoError(t, json.Unmarshal(encoded, &result))
				keys := result["keys"].([]any)
				require.Len(t, keys, 3)
				for i, key := range keys {
					row := key.(map[string]any)
					require.Equal(t, "rust/packages", row["dimension"])
					require.Equal(t, fmt.Sprintf("crate-%d-%d", generation, i), row["key"])
					loaded, err := srv.Query(ctx, `query($id: ID!) { node(id: $id) { ... on ArtifactDimensionKey { dimension key } } }`, map[string]any{"id": row["id"]})
					require.NoError(t, err)
					encoded, err := json.Marshal(loaded)
					require.NoError(t, err)
					require.NoError(t, json.Unmarshal(encoded, &loaded))
					delete(row, "id")
					require.Equal(t, row, loaded["node"])
				}
			}
		})
	}
}

func BenchmarkDimensionKeyFieldReads(b *testing.B) {
	for _, count := range []int{3, 3078} {
		for _, direct := range []bool{false, true} {
			b.Run(fmt.Sprintf("%d/direct=%t", count, direct), func(b *testing.B) {
				ctx, srv := dimensionKeyFieldsFixture(b, count, direct)
				generation := 0
				b.ReportAllocs()
				for b.Loop() {
					generation++
					result, err := srv.Query(ctx, `query($generation: Int!) { keys(generation: $generation) { dimension key } }`, map[string]any{"generation": generation})
					require.NoError(b, err)
					require.Len(b, result["keys"], count)
				}
			})
		}
	}
}
