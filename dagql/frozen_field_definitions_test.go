package dagql

import (
	"context"
	"fmt"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql/call"
)

func frozenFixture(t testing.TB) *Server {
	t.Helper()
	srv := newDagqlServerForTest(t, &reflectedAccessorTestObject{})
	srv.View = "current"
	srv.Root().ObjectType().Extend(FieldSpec{
		Name: "value", Description: "original", Type: String(""),
		Args:       NewInputSpecs(InputSpec{Name: "input", Type: String(""), Default: String("hello"), Directives: ast.DirectiveList{{Name: "marker"}}}),
		Directives: ast.DirectiveList{{Name: "marker"}},
	}, nil)
	srv.InstallDirective(DirectiveSpec{Name: "marker", Locations: []DirectiveLocation{DirectiveLocationFieldDefinition, DirectiveLocationArgumentDefinition}})
	srv.FreezeFieldDefinitions("current")
	return srv
}

func TestFrozenFieldsRetainSnapshotAndMutationIsolation(t *testing.T) {
	parent := frozenFixture(t)
	child, err := parent.Fork(t.Context(), &reflectedAccessorTestObject{})
	require.NoError(t, err)
	// The child has not materialized the lazy snapshot when the parent writes.
	parent.Root().ObjectType().Extend(FieldSpec{Name: "value", Description: "parent", Type: Int(0)}, nil)
	require.Equal(t, "original", child.Schema().Query.Fields.ForName("value").Description)
	require.Equal(t, "parent", parent.Schema().Query.Fields.ForName("value").Description)
	grandchild, err := child.Fork(t.Context(), &reflectedAccessorTestObject{})
	require.NoError(t, err)
	grandchild.Root().ObjectType().Extend(FieldSpec{Name: "value", Description: "grandchild", Type: Int(0)}, nil)
	require.Equal(t, "grandchild", grandchild.Schema().Query.Fields.ForName("value").Description)
	require.Equal(t, "original", child.Schema().Query.Fields.ForName("value").Description)
	// Public definition callers still receive fresh field metadata.
	public := child.Root().ObjectType().(Definitive).TypeDefinition("current")
	field := public.Fields.ForName("value")
	field.Description = "changed"
	field.Type.NamedType = "Changed"
	field.Arguments[0].DefaultValue.Raw = "changed"
	field.Directives[0] = &ast.Directive{Name: "changed"}
	fresh := child.Schema().Query.Fields.ForName("value")
	require.Equal(t, "original", fresh.Description)
	require.Equal(t, "String", fresh.Type.NamedType)
	require.Equal(t, "hello", fresh.Arguments[0].DefaultValue.Raw)
	require.Equal(t, "marker", fresh.Directives[0].Name)
}

func TestFrozenFieldsKeepClientDirectiveFilteringPrivate(t *testing.T) {
	parent := frozenFixture(t)
	visible, err := parent.Fork(t.Context(), &reflectedAccessorTestObject{})
	require.NoError(t, err)
	visibleSchema := visible.Schema()
	require.Len(t, visibleSchema.Query.Fields.ForName("value").Directives, 1)
	hidden, err := parent.Fork(t.Context(), &reflectedAccessorTestObject{})
	require.NoError(t, err)
	hidden.InstallDirective(DirectiveSpec{Name: "marker", ViewFilter: ExactView("other")})
	hiddenSchema := hidden.Schema()
	require.Empty(t, hiddenSchema.Query.Fields.ForName("value").Directives)
	require.Empty(t, hiddenSchema.Query.Fields.ForName("value").Arguments[0].Directives)
	require.Same(t, hiddenSchema.Query, hiddenSchema.Types[hiddenSchema.Query.Name])
	require.Len(t, visibleSchema.Query.Fields.ForName("value").Directives, 1)
	require.Len(t, visibleSchema.Query.Fields.ForName("value").Arguments[0].Directives, 1)
	require.Len(t, parent.Schema().Query.Fields.ForName("value").Directives, 1)
}

func TestFrozenFieldsRespectViewAndConcurrentFirstUse(t *testing.T) {
	parent := frozenFixture(t)
	parent.Root().ObjectType().Extend(FieldSpec{Name: "futureOnly", Type: String(""), ViewFilter: ExactView("future")}, nil)
	parent.FreezeFieldDefinitions("current")
	require.Nil(t, parent.SchemaForView("current").Query.Fields.ForName("futureOnly"))
	require.NotNil(t, parent.SchemaForView("future").Query.Fields.ForName("futureOnly"))
	// A second fixture keeps its lazy descriptor unmaterialized for the race.
	parent = frozenFixture(t)
	var group sync.WaitGroup
	for range 16 {
		group.Go(func() {
			child, err := parent.Fork(t.Context(), &reflectedAccessorTestObject{})
			if err != nil {
				t.Error(err)
				return
			}
			if child.Schema().Query.Fields.ForName("value").Description != "original" {
				t.Error("wrong snapshot")
			}
		})
	}
	group.Wait()
}

type frozenBenchmarkObject struct{ name string }

func (o *frozenBenchmarkObject) Type() *ast.Type {
	if o == nil {
		return &ast.Type{NamedType: "FrozenBenchmarkRoot", NonNull: true}
	}
	return &ast.Type{NamedType: o.name, NonNull: true}
}

var frozenSchemaSink *ast.Schema

func BenchmarkFrozenFieldSchema(b *testing.B) {
	for _, count := range []int{16, 64} {
		for _, frozen := range []bool{false, true} {
			b.Run(fmt.Sprintf("types%d/frozen%t", count, frozen), func(b *testing.B) {
				root := &frozenBenchmarkObject{name: "FrozenBenchmarkRoot"}
				parent := newDagqlServerForTest(b, root)
				parent.View = call.View("current")
				for i := range count {
					class := NewClass(parent, ClassOpts[*frozenBenchmarkObject]{Typed: &frozenBenchmarkObject{name: fmt.Sprint("FrozenType", i)}, NoIDs: true})
					for j := range 32 {
						class.Extend(FieldSpec{Name: fmt.Sprint("field", j), Type: String(""), Args: NewInputSpecs(InputSpec{Name: "input", Type: String(""), Default: String("value")})}, nil)
					}
					parent.InstallObject(class)
				}
				if frozen {
					parent.FreezeFieldDefinitions("current")
				}
				parent.Schema()
				b.ReportAllocs()
				b.ResetTimer()
				for b.Loop() {
					child, err := parent.Fork(b.Context(), root)
					if err != nil {
						b.Fatal(err)
					}
					frozenSchemaSink = child.Schema()
				}
			})
		}
	}
}

// Embedding Class does not grant permission to bypass a wrapper's provider.
type frozenWrappedClass struct {
	Class[*frozenBenchmarkObject]
}

func (c frozenWrappedClass) TypeDefinition(view call.View) *ast.Definition {
	def := c.Class.TypeDefinition(view)
	def.Description = "wrapper provider"
	return def
}
func (c frozenWrappedClass) ForkObjectType(srv *Server) (ObjectType, error) {
	fork, err := c.Class.ForkObjectType(srv)
	if err != nil {
		return nil, err
	}
	return frozenWrappedClass{fork.(Class[*frozenBenchmarkObject])}, nil
}
func TestFrozenFieldsPreserveWrappedProvider(t *testing.T) {
	srv := newDagqlServerForTest(t, &reflectedAccessorTestObject{})
	class := NewClass(srv, ClassOpts[*frozenBenchmarkObject]{Typed: &frozenBenchmarkObject{name: "WrappedProvider"}, NoIDs: true})
	class.Extend(FieldSpec{Name: "value", Type: String("")}, nil)
	srv.InstallObject(frozenWrappedClass{class})
	srv.FreezeFieldDefinitions("")
	require.Equal(t, "wrapper provider", srv.Schema().Types["WrappedProvider"].Description)
	fork, err := srv.Fork(context.Background(), &reflectedAccessorTestObject{})
	require.NoError(t, err)
	require.Equal(t, "wrapper provider", fork.Schema().Types["WrappedProvider"].Description)
}
