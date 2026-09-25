package dangv2

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/stretchr/testify/require"
	"github.com/vito/dang/v2/pkg/introspection"
)

// Populate all mutable JSON fields, including usually absent mutation and
// subscription metadata. Round-trip through JSON to match the cached input.
func schemaCloneFixture(t testing.TB) ([]byte, *introspection.Response) {
	t.Helper()
	value := `"default"`
	directives := introspection.Directives{&introspection.Directive{Name: "sourceMap", Args: []*introspection.DirectiveArg{{Name: "filename", Value: &value}}}}
	ref := &introspection.TypeRef{Kind: introspection.TypeKindNonNull, OfType: &introspection.TypeRef{Kind: introspection.TypeKindScalar, Name: "String"}}
	input := introspection.InputValue{Name: "arg", DefaultValue: &value, TypeRef: ref, Directives: directives}
	schema := &introspection.Schema{
		Types: introspection.Types{&introspection.Type{
			Name: "Query", Kind: introspection.TypeKindObject,
			Fields:        []*introspection.Field{{Name: "hello", TypeRef: ref, Args: introspection.InputValues{input}, Directives: directives}},
			InputFields:   []introspection.InputValue{input},
			EnumValues:    []introspection.EnumValue{{Name: "ONE", Directives: directives}},
			Interfaces:    []*introspection.Type{{Name: "Node", Kind: introspection.TypeKindInterface}},
			PossibleTypes: []*introspection.Type{{Name: "Concrete", Kind: introspection.TypeKindObject}},
			Directives:    directives,
		}},
		Directives: []*introspection.DirectiveDef{{Name: "example", Locations: []string{"FIELD"}, Args: introspection.InputValues{input}}},
	}
	schema.QueryType.Name = "Query"
	// These are anonymous struct fields in the upstream schema model.
	schema.MutationType = &struct {
		Name string `json:"name,omitempty"`
	}{Name: "Mutation"}
	schema.SubscriptionType = &struct {
		Name string `json:"name,omitempty"`
	}{Name: "Subscription"}
	data, err := json.Marshal(introspection.Response{Schema: schema, SchemaVersion: "v1"})
	require.NoError(t, err)
	var decoded introspection.Response
	require.NoError(t, json.Unmarshal(data, &decoded))
	return data, &decoded
}

// Compare values and reject mutable pointer/slice aliasing recursively. This
// also catches shallow copies if the upstream model gains reference fields
// once those fields are represented in the fixture.
func assertSchemaIndependent(t *testing.T, a, b reflect.Value) {
	t.Helper()
	require.Equal(t, a.Type(), b.Type())
	switch a.Kind() {
	case reflect.Pointer:
		require.Equal(t, a.IsNil(), b.IsNil())
		if !a.IsNil() {
			require.NotEqual(t, a.Pointer(), b.Pointer(), a.Type().String())
			assertSchemaIndependent(t, a.Elem(), b.Elem())
		}
	case reflect.Slice:
		require.Equal(t, a.IsNil(), b.IsNil())
		require.Equal(t, a.Len(), b.Len())
		if a.Len() > 0 {
			require.NotEqual(t, a.Pointer(), b.Pointer())
		}
		for i := 0; i < a.Len(); i++ {
			assertSchemaIndependent(t, a.Index(i), b.Index(i))
		}
	case reflect.Struct:
		for i := 0; i < a.NumField(); i++ {
			assertSchemaIndependent(t, a.Field(i), b.Field(i))
		}
	default:
		require.Equal(t, a.Interface(), b.Interface())
	}
}

func TestCloneIntrospectionSchema(t *testing.T) {
	_, source := schemaCloneFixture(t)
	copy := cloneIntrospectionSchema(source.Schema)
	require.Equal(t, source.Schema, copy)
	assertSchemaIndependent(t, reflect.ValueOf(source.Schema), reflect.ValueOf(copy))
	copy.Types[0].Fields[0].ParentObject = copy.Types[0]
	copy.Types[0].Fields[0].TypeRef.OfType.Name = "Changed"
	*copy.Types[0].Fields[0].Args[0].DefaultValue = "changed"
	copy.ScrubType("Query")
	require.Equal(t, "String", source.Schema.Types[0].Fields[0].TypeRef.OfType.Name)
	require.Nil(t, source.Schema.Types[0].Fields[0].ParentObject)
	require.Len(t, source.Schema.Types, 1)
	require.Nil(t, cloneIntrospectionSchema(nil))
	require.Equal(t, &introspection.Schema{Types: introspection.Types{}}, cloneIntrospectionSchema(&introspection.Schema{Types: introspection.Types{}}))
}

func TestCachedDangSchema(t *testing.T) {
	_, original := schemaCloneFixture(t)
	ctx := t.Context()
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.Close(context.Background())) })
	var decodes atomic.Int64
	decode := func(context.Context) (*introspection.Response, error) { decodes.Add(1); return original, nil }
	var wg sync.WaitGroup
	for range 16 {
		wg.Go(func() {
			copy, err := cachedDangSchema(ctx, cache, "first", 1, decode)
			if err != nil {
				t.Error(err)
				return
			}
			if copy.Schema.Types[0].Fields[0].Name != "hello" {
				t.Error("shared mutation")
			}
			copy.Schema.Types[0].Fields[0].Name = "changed"
		})
	}
	wg.Wait()
	require.EqualValues(t, 1, decodes.Load())
	for _, tc := range []struct {
		session string
		file    uint64
	}{{"first", 2}, {"second", 1}} {
		_, err := cachedDangSchema(ctx, cache, tc.session, tc.file, decode)
		require.NoError(t, err)
	}
	require.EqualValues(t, 3, decodes.Load(), "different files or sessions must decode separately")
	_, err = cachedDangSchema(ctx, cache, "first", 3, func(context.Context) (*introspection.Response, error) { return nil, errors.New("broken JSON") })
	require.ErrorContains(t, err, "broken JSON")
	_, err = cachedDangSchema(ctx, cache, "first", 3, decode)
	require.NoError(t, err, "failed initialization must not poison the cache")
	require.EqualValues(t, 4, decodes.Load())
	require.NoError(t, cache.ReleaseSession(ctx, "first"))
	require.NoError(t, cache.WaitSessionRelease(ctx, "first"))
	_, err = cachedDangSchema(ctx, cache, "first", 1, decode)
	require.ErrorIs(t, err, dagql.ErrCacheSessionReleased)
}

func BenchmarkDangSchemaDecode(b *testing.B) {
	_, fixture := schemaCloneFixture(b)
	for _, count := range []int{100, 500} {
		schema := cloneIntrospectionSchema(fixture.Schema)
		for i := 1; i < count; i++ {
			typ := cloneIntrospectionType(fixture.Schema.Types[0])
			typ.Name = fmt.Sprintf("Type%d", i)
			schema.Types = append(schema.Types, typ)
		}
		data, err := json.Marshal(&introspection.Response{Schema: schema})
		require.NoError(b, err)
		b.Run(fmt.Sprintf("types=%d/decode", count), func(b *testing.B) {
			b.ReportAllocs()
			for b.Loop() {
				var decoded introspection.Response
				if err := json.NewDecoder(bytes.NewReader(data)).Decode(&decoded); err != nil {
					b.Fatal(err)
				}
			}
		})
		b.Run(fmt.Sprintf("types=%d/clone", count), func(b *testing.B) {
			b.ReportAllocs()
			for b.Loop() {
				_ = cloneIntrospectionSchema(schema)
			}
		})
	}
}
