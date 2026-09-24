package artifact

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestDimensionNames(t *testing.T) {
	dims := Dimensions{
		{Identifier: "Golang.modules", Name: "go-module", QualifiedName: "golang-modules"},
		{Identifier: "App.dependencies", Name: "go-module", QualifiedName: "app-dependencies"},
	}
	for _, tc := range []struct{ name, id string }{
		{"Golang.modules", "Golang.modules"},
		{"golang-modules", "Golang.modules"},
		{"app-dependencies", "App.dependencies"},
		{"missing", "missing"},
	} {
		id, err := dims.Resolve(tc.name)
		require.NoError(t, err)
		require.Equal(t, tc.id, id)
	}
	_, err := dims.Resolve("go-module")
	require.EqualError(t, err, `ambiguous dimension "go-module": use Golang.modules or App.dependencies`)
	require.Equal(t, "golang-modules", dims.DisplayName(dims[0]))
	require.Equal(t, "app-dependencies", dims.DisplayName(dims[1]))
	require.Equal(t, "go-module", dims[:1].DisplayName(dims[0]))

	// An alias can also conflict with another dimension's qualified name.
	dims = append(dims, &Dimension{Identifier: "Other.modules", Name: "golang-modules", QualifiedName: "golang-modules"})
	require.Equal(t, "Golang.modules", dims.DisplayName(dims[0]))
}

func TestDimensionNameIndex(t *testing.T) {
	dims := Dimensions{
		{Identifier: "A.items", Name: "item", QualifiedName: "a-items"},
		{Identifier: "B.items", Name: "item", QualifiedName: "b-items"},
		{Identifier: "C.items", Name: "a-items", QualifiedName: "a-items"},
		{Identifier: "D.items", Name: "A.items", QualifiedName: "d-items"},
	}
	for i := range 16 {
		dims = append(dims, &Dimension{Identifier: fmt.Sprintf("Extra.items%d", i), Name: "item", QualifiedName: fmt.Sprintf("extra-items%d", i)})
	}
	for size := 0; size <= len(dims); size++ {
		scope := dims[:size]
		index := scope.IndexNames()
		for _, dim := range append(append(Dimensions{}, dims...), &Dimension{
			Identifier: "A.items", Name: "renamed", QualifiedName: "a-items",
		}) {
			require.Equal(t, scope.DisplayName(dim), index.DisplayName(dim))
		}
	}
}
