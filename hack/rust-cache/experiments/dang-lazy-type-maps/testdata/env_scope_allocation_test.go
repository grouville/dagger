package dang

import (
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vito/dang/v2/pkg/hm"
)

func TestTypeScopeLocalState(t *testing.T) {
	parent := NewType("Parent", ObjectKind)
	scheme := hm.NewScheme(nil, StringType)
	object := NewType("Nested", ObjectKind)
	directive := &DirectiveDecl{}
	applications := []*DirectiveApplication{{}}
	origin := ImportedBindingOrigin("Upstream", false)
	parent.Add("value", scheme)
	parent.AddObject("Nested", object)
	parent.AddDirective("marker", directive)
	parent.SetDocString("value", "parent documentation")
	parent.SetDirectives("value", applications)
	parent.SetVisibility("value", PublicVisibility)

	child := parent.Clone().(*Type)
	gotScheme, found := child.SchemeOf("value")
	require.True(t, found)
	require.Same(t, scheme, gotScheme)
	gotObject, found := child.NamedType("Nested")
	require.True(t, found)
	require.Same(t, object, gotObject)
	gotDirective, found := child.GetDirective("marker")
	require.True(t, found)
	require.Same(t, directive, gotDirective)
	gotDoc, found := child.GetDocString("value")
	require.True(t, found)
	require.Equal(t, "parent documentation", gotDoc)
	require.Equal(t, applications, child.GetDirectives("value"))
	_, found = child.LocalSchemeOf("value")
	require.False(t, found)
	_, found = child.LocalNamedType("Nested")
	require.False(t, found)
	_, found = child.LocalValueOrigin("value")
	require.False(t, found)

	// Metadata setters can precede a declaration. Add must preserve explicit
	// visibility and reset the declaration's origin to local.
	child.SetValueOrigin("value", origin)
	child.SetTypeOrigin("Nested", origin)
	child.SetDirectiveOrigin("marker", origin)
	gotOrigin, found := child.LocalValueOrigin("value")
	require.True(t, found)
	require.Equal(t, origin, gotOrigin)
	gotOrigin, found = child.LocalTypeOrigin("Nested")
	require.True(t, found)
	require.Equal(t, origin, gotOrigin)
	gotOrigin, found = child.LocalDirectiveOrigin("marker")
	require.True(t, found)
	require.Equal(t, origin, gotOrigin)
	child.SetVisibility("value", PrivateVisibility)
	child.Add("value", hm.NewScheme(nil, IntType))
	child.AddObject("Nested", NewType("Replacement", ObjectKind))
	child.AddDirective("marker", &DirectiveDecl{})
	child.SetDocString("value", "child documentation")
	child.SetDirectives("value", nil)
	require.Equal(t, PrivateVisibility, child.Visibility("value"))
	gotOrigin, found = child.LocalValueOrigin("value")
	require.True(t, found)
	require.Equal(t, LocalBindingOrigin(), gotOrigin)
	gotOrigin, found = child.LocalTypeOrigin("Nested")
	require.True(t, found)
	require.Equal(t, LocalBindingOrigin(), gotOrigin)
	gotOrigin, found = child.LocalDirectiveOrigin("marker")
	require.True(t, found)
	require.Equal(t, LocalBindingOrigin(), gotOrigin)
	require.Nil(t, child.GetDirectives("value"))
	gotDoc, found = child.GetDocString("value")
	require.True(t, found)
	require.Equal(t, "child documentation", gotDoc)

	gotScheme, found = parent.LocalSchemeOf("value")
	require.True(t, found)
	require.Same(t, scheme, gotScheme)
	gotObject, found = parent.LocalNamedType("Nested")
	require.True(t, found)
	require.Same(t, object, gotObject)
	gotDirective, found = parent.GetDirective("marker")
	require.True(t, found)
	require.Same(t, directive, gotDirective)
	gotDoc, found = parent.GetDocString("value")
	require.True(t, found)
	require.Equal(t, "parent documentation", gotDoc)
	require.Equal(t, PublicVisibility, parent.Visibility("value"))
	require.Equal(t, applications, parent.GetDirectives("value"))
}

var benchmarkTypeScope *Type

func BenchmarkTypeScope(b *testing.B) {
	parent := NewType("Parent", ObjectKind)
	scheme := hm.NewScheme(nil, StringType)
	parent.Add("outer", scheme)
	for _, test := range []struct {
		name string
		make func() *Type
	}{
		{"empty", func() *Type { return NewType("", ObjectKind) }},
		{"clone", func() *Type { return parent.Clone().(*Type) }},
		{"binding", func() *Type {
			scope := parent.Clone().(*Type)
			scope.Add("inner", scheme)
			return scope
		}},
	} {
		b.Run(test.name, func(b *testing.B) {
			b.ReportAllocs()
			for b.Loop() {
				benchmarkTypeScope = test.make()
			}
		})
	}
}
