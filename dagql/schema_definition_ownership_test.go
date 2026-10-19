package dagql

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql/call"
)

type retainedDefinition struct{ def *ast.Definition }

func (d retainedDefinition) TypeName() string                         { return d.def.Name }
func (d retainedDefinition) TypeDefinition(call.View) *ast.Definition { return d.def }

func TestSchemaViewPreservesProvidedDefinition(t *testing.T) {
	for _, first := range []call.View{"old", "future"} {
		t.Run(string(first), func(t *testing.T) {
			srv := newDagqlServerForTest(t, &reflectedAccessorTestObject{})
			marker := func() ast.DirectiveList { return ast.DirectiveList{{Name: "futureOnly"}} }
			provided := &ast.Definition{Kind: ast.Object, Name: "RetainedDefinition", Directives: marker(), Fields: ast.FieldList{{Name: "value", Type: String("").Type(), Directives: marker(), Arguments: ast.ArgumentDefinitionList{{Name: "input", Type: String("").Type(), Directives: marker()}}}}}
			srv.InstallTypeDef(retainedDefinition{provided})
			srv.InstallDirective(DirectiveSpec{Name: "futureOnly", ViewFilter: ExactView("future"), Locations: []DirectiveLocation{DirectiveLocationObject, DirectiveLocationFieldDefinition, DirectiveLocationArgumentDefinition}})
			srv.Root().ObjectType().Extend(FieldSpec{Name: "rootValue", Type: String(""), Directives: marker()}, nil)
			second := call.View("future")
			if first == "future" {
				second = "old"
			}
			for _, view := range []call.View{first, second, first} {
				schema := srv.SchemaForView(view)
				def := schema.Types[provided.Name]
				count := 0
				if view == "future" {
					count = 1
				}
				require.Len(t, def.Directives, count)
				require.Len(t, def.Fields[0].Directives, count)
				require.Len(t, def.Fields[0].Arguments[0].Directives, count)
				require.Same(t, schema.Query, schema.Types[schema.Query.Name])
				require.Len(t, schema.Query.Fields.ForName("rootValue").Directives, count)
				for _, definitions := range schema.PossibleTypes {
					for _, possible := range definitions {
						require.Same(t, schema.Types[possible.Name], possible)
					}
				}
			}
			require.Len(t, provided.Directives, 1)
			require.Len(t, provided.Fields[0].Directives, 1)
			require.Len(t, provided.Fields[0].Arguments[0].Directives, 1)
		})
	}
}
