package schema

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/dagger/dagger/dagql"

	"github.com/dagger/dagger/core"
	"github.com/stretchr/testify/require"
)

func TestArtifactTypeDefinitionsStayStatic(t *testing.T) {
	result, err := dagql.NewResultForCall(&core.TypeDef{Name: "Container", Kind: core.TypeDefKindObject}, &dagql.ResultCall{})
	require.NoError(t, err)
	typ := dagql.ObjectResult[*core.TypeDef]{Result: result}
	all := &core.Artifacts{Entries: []*core.Artifact{{
		Path: []string{"items", "broken"}, TypeName: "Container",
		Node: &core.ModTreeNode{Type: typ, Parent: &core.ModTreeNode{
			CollectionDimension: &core.ArtifactDimension{Identifier: "App.items"},
		}},
	}}}
	// An unbound collection with no receiver/server would fail if expanded.
	// Type commands must still be discoverable, even with a runtime key filter.
	for _, selection := range []*core.Artifacts{all, all.FilterDimensionKeys("App.items", []string{"unknown"})} {
		definitions, err := (&artifactsSchema{}).typeDefinitions(t.Context(), selection, struct{}{})
		require.NoError(t, err)
		require.Len(t, definitions, 1)
		require.Equal(t, "Container", definitions[0].Self().Name)
	}
}

func TestArtifactItemsJSON(t *testing.T) {
	key := "space & / unicode: λ"
	dimension := &core.ArtifactDimension{Identifier: "App.items", Name: "item", QualifiedName: "app-items"}
	all := &core.Artifacts{Entries: []*core.Artifact{
		{Path: []string{"items", "check"}, TypeName: "Check", Node: &core.ModTreeNode{
			Name: "check", Description: "Check this item.\nMore detail.",
			Parent: &core.ModTreeNode{Name: "get", CollectionDimension: dimension, CollectionKey: &key},
		}},
		{Path: []string{"static"}, TypeName: "Container", Node: &core.ModTreeNode{Name: "static", Description: "Deferred container"}},
		{Path: []string{"broken", "load"}, TypeName: "Check", LoadFailure: &core.ModuleLoadFailure{}},
	}}
	schema := &artifactsSchema{}
	for _, selection := range []*core.Artifacts{all, {}} {
		for _, typed := range []bool{false, true} {
			got, err := schema.itemsJSON(t.Context(), selection, artifactItemsJSONArgs{TypeAssertion: typed})
			require.NoError(t, err)
			// Build the same response through the public per-object API.
			items, err := schema.items(t.Context(), selection, struct{}{})
			require.NoError(t, err)
			want := make([]map[string]any, 0, len(items))
			for _, item := range items {
				uri, err := item.URI(core.ArtifactURIOpts{TypeAssertion: typed, DimensionKeys: true})
				require.NoError(t, err)
				description, err := schema.description(t.Context(), item, struct{}{})
				require.NoError(t, err)
				keys := make([]map[string]string, 0, len(item.DimensionKeys))
				for _, key := range item.DimensionKeys {
					keys = append(keys, map[string]string{"dimension": key.Dimension, "key": key.Key})
				}
				want = append(want, map[string]any{"uri": uri, "description": description, "dimensionKeys": keys})
			}
			encoded, err := json.Marshal(want)
			require.NoError(t, err)
			require.JSONEq(t, string(encoded), string(got))
		}
	}
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	_, err := schema.itemsJSON(ctx, all, artifactItemsJSONArgs{})
	require.ErrorIs(t, err, context.Canceled)
}

func TestArtifactDirectiveFilterDoesNotRequireWorkspace(t *testing.T) {
	// Raw metadata filters must work without workspace settings or valid
	// command result types. Command filters enforce those rules separately.
	check := &core.Artifact{Path: []string{"check"}, TypeName: "Container", Directives: []string{"check"}}
	other := &core.Artifact{Path: []string{"other"}, TypeName: "Check"}
	all := &core.Artifacts{Entries: []*core.Artifact{check, other}}
	schema := &artifactsSchema{}
	included, err := schema.filterDirectives(t.Context(), all, artifactDirectiveFilterArgs{Directives: []string{"check"}})
	require.NoError(t, err)
	require.Equal(t, []*core.Artifact{check}, included.Entries)
	excluded, err := schema.filterDirectives(t.Context(), all, artifactDirectiveFilterArgs{Directives: []string{"check"}, Exclude: true})
	require.NoError(t, err)
	require.Equal(t, []*core.Artifact{other}, excluded.Entries)
}

func TestArtifactTypedConversion(t *testing.T) {
	for _, tc := range []struct {
		name       string
		entries    []*core.Artifact
		wantErr    string
		wantValues int
	}{
		{name: "unmarked changeset", entries: []*core.Artifact{{TypeName: "Changeset", Path: []string{"edit"}}}, wantValues: 1},
		{name: "empty"},
		{name: "reject mixed selection before evaluation", entries: []*core.Artifact{
			{TypeName: "Changeset", Path: []string{"edit"}},
			{TypeName: "Service", Path: []string{"serve"}},
		}, wantErr: "dag://serve is a Service, not changeset"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			ctx, srv, _, _ := resolverOutputFixture(t)
			srv.InstallObject(dagql.NewClass[*core.Artifacts](srv))
			srv.InstallObject(dagql.NewClass[*core.Artifact](srv))
			srv.InstallObject(dagql.NewClass[*core.Changeset](srv))
			schema := &artifactsSchema{}
			dagql.Fields[*core.Artifacts]{
				dagql.Func("items", schema.items),
				dagql.NodeFunc("asChangesets", schema.asChangesets),
			}.Install(srv)
			evaluations := 0
			dagql.Fields[*core.Artifact]{dagql.Func("value", func(context.Context, *core.Artifact, struct{}) (*core.Changeset, error) {
				evaluations++
				return &core.Changeset{}, nil
			})}.Install(srv)
			dagql.Fields[*core.Query]{dagql.Func("selection", func(context.Context, *core.Query, struct{}) (*core.Artifacts, error) {
				return &core.Artifacts{Entries: tc.entries}, nil
			})}.Install(srv)
			var result dagql.ObjectResultArray[*core.Changeset]
			err := srv.Select(ctx, srv.Root(), &result, dagql.Selector{Field: "selection"}, dagql.Selector{Field: "asChangesets"})
			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
			} else {
				require.NoError(t, err)
				require.Len(t, result, tc.wantValues)
			}
			require.Equal(t, tc.wantValues, evaluations)
		})
	}
}
