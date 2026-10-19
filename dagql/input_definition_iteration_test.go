package dagql

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql/call"
)

func TestArgumentDefinitionSelection(t *testing.T) {
	for _, padding := range []int{0, 16} {
		t.Run(fmt.Sprint(padding), func(t *testing.T) {
			raw := []InputSpec{
				{Name: "alpha", Type: String(""), Description: "first"},
				{Name: "beta", Type: Int(0), Default: Int(7)},
				{Name: "alpha", Type: String(""), Description: "new", ViewFilter: ExactView("new")},
				{Name: "gamma", Type: Boolean(false), ViewFilter: ExactView("old")},
			}
			for i := range padding {
				raw = append(raw, InputSpec{Name: fmt.Sprint("hidden", i), Type: String(""), ViewFilter: ExactView("hidden")})
			}
			specs := NewInputSpecs(raw...)
			for _, view := range []call.View{"old", "new"} {
				defs := specs.ArgumentDefinitions(view)
				names := []string{}
				for _, d := range defs {
					names = append(names, d.Name)
				}
				if view == "old" {
					require.Equal(t, []string{"alpha", "beta", "gamma"}, names)
					require.Equal(t, "first", defs[0].Description)
				} else {
					require.Equal(t, []string{"beta", "alpha"}, names)
					require.Equal(t, "new", defs[1].Description)
				}
				selected := specs.Inputs(view)
				for i, arg := range selected {
					require.Equal(t, arg.Name, defs[i].Name)
					require.Equal(t, arg.Type.Type(), defs[i].Type)
					if arg.Default != nil {
						require.Equal(t, arg.Default.ToLiteral().ToAST(), defs[i].DefaultValue)
					}
				}
			}
		})
	}
}

func TestArgumentDefinitionMetadataOwnership(t *testing.T) {
	reason := "use replacement"
	specs := NewInputSpecs(InputSpec{
		Name:               "value",
		Type:               String(""),
		Default:            String("default"),
		Description:        "description",
		DeprecatedReason:   &reason,
		ExperimentalReason: "preview",
		Internal:           true,
		Directives:         ast.DirectiveList{{Name: "custom"}},
	})
	first := specs.ArgumentDefinitions("")
	require.Equal(t, []string{"custom", "deprecated", "experimental", "internal"}, []string{first[0].Directives[0].Name, first[0].Directives[1].Name, first[0].Directives[2].Name, first[0].Directives[3].Name})
	first[0].Name = "changed"
	first[0].Directives[0] = &ast.Directive{Name: "changed"}
	again := specs.ArgumentDefinitions("")
	require.Equal(t, "value", again[0].Name)
	require.Equal(t, "custom", again[0].Directives[0].Name)
	empty := NewInputSpecs().ArgumentDefinitions("")
	require.NotNil(t, empty)
	require.Empty(t, empty)
}

var argumentDefinitionSink []*ast.ArgumentDefinition
var inputSpecSink []InputSpec

func BenchmarkInputDefinitionIteration(b *testing.B) {
	for _, count := range []int{1, 8, 16, 64} {
		specs := NewInputSpecs()
		for i := range count {
			specs.Add(InputSpec{Name: fmt.Sprint("arg", i), Type: String(""), Default: String("value"), Description: "an input"})
		}
		b.Run(fmt.Sprint(count), func(b *testing.B) {
			b.Run("definitions", func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					argumentDefinitionSink = specs.ArgumentDefinitions("")
				}
			})
			b.Run("inputs", func(b *testing.B) {
				b.ReportAllocs()
				for b.Loop() {
					inputSpecSink = specs.Inputs("")
				}
			})
		})
	}
}
