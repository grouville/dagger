package core

import (
	"context"

	"dagger.io/dagger/core"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

func (CollectionsSuite) TestCollectionEvaluationKeepsWorkspaceScope(ctx context.Context, t *testctx.T) {
	c := connect(ctx, t)
	dag := core.NewQuery(c)
	module := dag.Directory().
		WithNewFile("dagger-module.toml", "name = \"scope\"\nengineVersion = \"v1.0.0-0\"\n[runtime]\nsource = \"dang\"\n").
		WithNewFile("main.dang", `type Scope {
  items(ws: Workspace!): Items! { Items(names: [ws.file("marker.txt").contents]) }
}
type Items @collection {
  names: [String!]! @keys
  get(key: String!): Item! { Item(key) }
}
type Item {
  key: String!
  first(ws: Workspace!): Void @check {
    if (ws.file("marker.txt").contents != key) { raise "wrong workspace" }
    null
  }
  second(ws: Workspace!): Void @check {
    if (ws.file("marker.txt").contents == "edited") { raise "edited workspace" }
    null
  }
}
`)
	base := dag.Directory().
		WithNewFile("dagger.toml", "[modules.scope]\nsource = \"./scope\"\n").
		WithDirectory("scope", module)
	other := base.WithNewFile("marker.txt", "B").AsWorkspace().Artifacts()
	for _, value := range []string{"A", "edited", "A"} {
		selected := base.WithNewFile("marker.txt", value).AsWorkspace().Artifacts().
			WithArtifacts(other).FilterTypes([]string{"Check"})
		keys, err := selected.DimensionKeys(ctx, "/scope/items")
		require.NoError(t, err)
		require.ElementsMatch(t, []string{value, "B"}, keys)
		results, err := selected.Values(ctx, core.ArtifactsValuesOpts{MaxConcurrency: 2})
		require.NoError(t, err)
		require.Len(t, results, 4)
		failures := 0
		for _, result := range results {
			failure, err := result.Error(ctx)
			require.NoError(t, err)
			if failure != nil {
				message, err := failure.Message(ctx)
				require.NoError(t, err)
				require.Contains(t, message, "edited workspace")
				failures++
			}
		}
		if value == "edited" {
			require.Equal(t, 1, failures)
		} else {
			require.Zero(t, failures)
		}
	}
}
