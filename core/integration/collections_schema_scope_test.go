package core

import (
	"context"

	"dagger.io/dagger/core"
	"github.com/dagger/testctx"
	"github.com/stretchr/testify/require"
)

func (CollectionsSuite) TestCollectionDiscoveryKeepsWorkspaceScope(ctx context.Context, t *testctx.T) {
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
  first: Void @check { null }
  second: Void @check { null }
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
	}
}
