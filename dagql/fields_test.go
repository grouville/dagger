package dagql

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql/call"
)

type reflectedAccessorTestObject struct {
	Value    int                          `field:"true"`
	Name     string                       `field:"true"`
	Ratio    float64                      `field:"true"`
	Enabled  bool                         `field:"true"`
	Optional *string                      `field:"true"`
	Child    *reflectedAccessorTestObject `field:"true"`
	Names    []string                     `field:"true"`
}

func (*reflectedAccessorTestObject) Type() *ast.Type {
	return &ast.Type{NamedType: "ReflectedAccessorTestObject", NonNull: true}
}

func TestFieldsInstallMarksReflectedAccessorsTrivial(t *testing.T) {
	srv := newDagqlServerForTest(t, &reflectedAccessorTestObject{})
	Fields[*reflectedAccessorTestObject]{}.Install(srv)

	obj, ok := srv.ObjectType("ReflectedAccessorTestObject")
	require.True(t, ok)
	for _, name := range []string{"value", "name", "ratio", "enabled", "optional", "child", "names"} {
		spec, ok := obj.FieldSpec(name, call.View(""))
		require.True(t, ok, name)
		require.True(t, spec.Trivial, name)
		require.False(t, spec.NoTelemetry, name)
		if name == "value" || name == "name" || name == "ratio" || name == "enabled" {
			require.NotEmpty(t, spec.DoNotCache, name)
		} else {
			require.Empty(t, spec.DoNotCache, name)
		}
	}
}
