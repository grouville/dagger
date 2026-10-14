package core

import (
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func TestModuleObjectInlineFieldLifetime(t *testing.T) {
	ctx := engine.ContextWithClientMetadata(t.Context(), &engine.ClientMetadata{ClientID: "inline-producer", SessionID: "typedef-test-session"})
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.CloseDiscardingPersistence()) })
	root := &Query{}
	server := &moduleObjectTestServer{mockServer: &mockServer{}, cache: cache, root: root}
	root.Server = server
	dag := newCoreDagqlServerForTest(t, root)
	server.dag = dag
	ctx = dagql.ContextWithCache(ContextWithQuery(ctx, root), cache)
	installModuleObjectTestModuleClass(dag)
	installTypeDefTestClasses(dag)
	installModuleObjectHandleTestObjClass(dag)

	childDef := NewObjectTypeDef("Child", "", nil)
	childType := newTypeDefDetachedResult(t, dag, "child-type", (&TypeDef{}).WithObjectTypeDef(
		newTypeDefDetachedResult(t, dag, "child-def", childDef),
	))
	parentDef := NewObjectTypeDef("Parent", "", nil)
	parentDef.Fields = append(parentDef.Fields, newTypeDefDetachedResult(t, dag, "child-field", NewFieldTypeDef("child", childType, "", nil)))
	optionalChild := newTypeDefDetachedResult(t, dag, "optional-child-type", childType.Self().WithOptional(true))
	childrenType := newTypeDefDetachedResult(t, dag, "children-type", (&TypeDef{}).WithListOf(
		newTypeDefDetachedResult(t, dag, "children-list", &ListTypeDef{ElementTypeDef: childType}),
	))
	parentDef.Fields = append(parentDef.Fields,
		newTypeDefDetachedResult(t, dag, "optional-field", NewFieldTypeDef("optional", optionalChild, "", nil)),
		newTypeDefDetachedResult(t, dag, "children-field", NewFieldTypeDef("children", childrenType, "", nil)),
	)
	source := newTypeDefAttachedResult(t, ctx, cache, dag, "inline-source", &ModuleSource{
		Kind: ModuleSourceKindLocal, Local: &LocalModuleSource{ContextDirectoryPath: "/test"},
	})
	mod := newTypeDefAttachedResult(t, ctx, cache, dag, "inline-module", &Module{
		NameField: "Test", OriginalName: "Test", Source: dagql.NonNull(source), Deps: NewSchemaBuilder(root, nil),
		ObjectDefs: dagql.ObjectResultArray[*TypeDef]{
			childType,
			newTypeDefDetachedResult(t, dag, "parent-type", (&TypeDef{}).WithObjectTypeDef(
				newTypeDefDetachedResult(t, dag, "parent-def", parentDef),
			)),
		},
	})
	for _, def := range []*ObjectTypeDef{parentDef, childDef} {
		require.NoError(t, (&ModuleObject{Module: mod, TypeDef: def}).Install(ctx, dag, InstallOpts{SkipConstructor: true}))
	}
	leaf := newTypeDefAttachedResult(t, ctx, cache, dag, "inline-leaf", &moduleObjectHandleTestObj{Value: "retained"})
	leafID, err := leaf.ID()
	require.NoError(t, err)
	encoded, err := leafID.Encode()
	require.NoError(t, err)
	parent := newTypeDefAttachedResult(t, ctx, cache, dag, "inline-parent", &ModuleObject{
		Module: mod, TypeDef: parentDef,
		Fields: map[string]any{
			"child":    map[string]any{"leaf": encoded},
			"optional": map[string]any{"leaf": encoded},
			"children": []any{map[string]any{"leaf": encoded}},
		},
	})
	parentID, err := parent.ID()
	require.NoError(t, err)
	var child dagql.ObjectResult[*ModuleObject]
	require.NoError(t, dag.Select(ctx, parent, &child, dagql.Selector{Field: "child"}))
	childID, err := child.ID()
	require.NoError(t, err)
	_, release, err := cache.HoldEntry(ctx, childID.EngineResultID())
	require.NoError(t, err)
	require.NoError(t, cache.ReleaseSession(ctx, "typedef-test-session"))

	reader := engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{ClientID: "inline-reader", SessionID: "inline-reader"})
	loaded, err := cache.LoadResultByResultID(reader, "inline-reader", dag, childID.EngineResultID())
	require.NoError(t, err)
	value, ok := dagql.UnwrapAs[*ModuleObject](loaded)
	require.True(t, ok)
	storedLeaf, ok := value.Fields["leaf"].(dagql.AnyResult)
	require.True(t, ok)
	var contents dagql.String
	require.NoError(t, dag.Select(reader, storedLeaf.(dagql.AnyObjectResult), &contents, dagql.Selector{Field: "value"}))
	require.Equal(t, "retained", contents.String())
	require.NoError(t, cache.ReleaseSession(reader, "inline-reader"))
	require.NoError(t, release(ctx))

	for _, id := range []uint64{parentID.EngineResultID(), childID.EngineResultID(), leafID.EngineResultID()} {
		_, release, err := cache.HoldEntry(ctx, id)
		if err == nil {
			require.NoError(t, release(ctx))
		}
		require.ErrorIs(t, err, dagql.ErrUnknownEntry, "result %d survived its final owner", id)
	}
}
