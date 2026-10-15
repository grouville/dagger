package dangv2

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"
)

const decodedSchemaFixture = `{"__schema":{
 "queryType":{"name":"Query"},"mutationType":{"name":"Mutation"},"subscriptionType":{"name":"Subscription"},
 "types":[{"kind":"OBJECT","name":"Query","description":"query",
  "fields":[{"name":"field","description":"field","type":{"kind":"NON_NULL","ofType":{"kind":"SCALAR","name":"String"}},
   "args":[{"name":"arg","description":"arg","defaultValue":"value","type":{"kind":"SCALAR","name":"String"},"directives":[{"name":"argDirective","args":[{"name":"reason","value":"arg"}]}]}],
   "isDeprecated":true,"deprecationReason":"old","directives":[{"name":"fieldDirective","args":[{"name":"reason","value":"field"}]}]}],
  "inputFields":[{"name":"input","defaultValue":"input","type":{"kind":"SCALAR","name":"String"},"directives":[{"name":"inputDirective","args":[{"name":"reason","value":"input"}]}]}],
  "enumValues":[{"name":"ENUM","description":"enum","isDeprecated":true,"deprecationReason":"old","directives":[{"name":"enumDirective","args":[{"name":"reason","value":"enum"}]}]}],
  "interfaces":[{"kind":"INTERFACE","name":"Node","fields":[]}],
  "possibleTypes":[{"kind":"OBJECT","name":"Possible","inputFields":[]}],
  "directives":[{"name":"typeDirective","args":[{"name":"reason","value":"type"}]}]}],
 "directives":[{"name":"definition","description":"directive","locations":["FIELD"],"args":[{"name":"arg","defaultValue":"default","type":{"kind":"SCALAR","name":"String"},"directives":[{"name":"nested","args":[{"name":"reason","value":"nested"}]}]}]}]
}}`

func TestDecodedSchemaCacheCopies(t *testing.T) {
	cache := newDecodedSchemaCache(2)
	data := []byte(decodedSchemaFixture)
	expected, err := decodeDangSchema(bytes.NewReader(data))
	require.NoError(t, err)
	first, err := cache.read(bytes.NewReader(data))
	require.NoError(t, err)
	require.Equal(t, expected, first)
	mutateDecodedSchema(reflect.ValueOf(first))
	second, err := cache.read(bytes.NewReader(data))
	require.NoError(t, err)
	require.Equal(t, expected, second, "the first caller must not mutate the cached schema")
	mutateDecodedSchema(reflect.ValueOf(second))
	third, err := cache.read(bytes.NewReader(data))
	require.NoError(t, err)
	require.Equal(t, expected, third, "a hit must also return an independent tree")

	cache.entries.Purge()
	var wg sync.WaitGroup
	for range 16 {
		wg.Go(func() {
			copy, err := cache.read(bytes.NewReader(data))
			if err != nil {
				t.Error(err)
				return
			}
			if !reflect.DeepEqual(expected, copy) {
				t.Error("concurrent caller received a modified schema")
			}
			mutateDecodedSchema(reflect.ValueOf(copy))
		})
	}
	wg.Wait()
}

// Mutating every leaf catches shared pointers and slice backing arrays,
// including optional default values and nested directive arguments.
func mutateDecodedSchema(v reflect.Value) {
	switch v.Kind() {
	case reflect.Pointer:
		if !v.IsNil() {
			mutateDecodedSchema(v.Elem())
		}
	case reflect.Struct:
		for i := range v.NumField() {
			mutateDecodedSchema(v.Field(i))
		}
	case reflect.Slice:
		for i := range v.Len() {
			mutateDecodedSchema(v.Index(i))
		}
	case reflect.String:
		v.SetString("modified")
	case reflect.Bool:
		v.SetBool(!v.Bool())
	}
}

func TestDecodedSchemaCacheBoundsAndChanges(t *testing.T) {
	cache := newDecodedSchemaCache(2)
	for _, name := range []string{"first", "second", "third"} {
		data := []byte(strings.ReplaceAll(decodedSchemaFixture, `"Query"`, fmt.Sprintf("%q", name)))
		schema, err := cache.read(bytes.NewReader(data))
		require.NoError(t, err)
		require.Equal(t, name, schema.QueryType.Name)
	}
	require.Equal(t, 2, cache.entries.Len())
	first := []byte(strings.ReplaceAll(decodedSchemaFixture, `"Query"`, `"first"`))
	require.False(t, cache.entries.Contains(sha256.Sum256(first)))

	large := decodedSchemaFixture + strings.Repeat(" ", maxCachedSchemaBytes)
	schema, err := cache.read(strings.NewReader(large))
	require.NoError(t, err)
	require.Equal(t, "Query", schema.QueryType.Name)
	require.Equal(t, 2, cache.entries.Len(), "large schemas must bypass retention")
	_, err = cache.read(strings.NewReader(`{"__schema":`))
	require.Error(t, err)
	require.Equal(t, 2, cache.entries.Len(), "decode errors must not be cached")
}

func BenchmarkDecodedSchemaCache(b *testing.B) {
	var schema map[string]any
	if err := json.Unmarshal([]byte(decodedSchemaFixture), &schema); err != nil {
		b.Fatal(err)
	}
	query := schema["__schema"].(map[string]any)["types"].([]any)[0].(map[string]any)
	field := query["fields"].([]any)[0]
	fields := make([]any, 1024)
	for i := range fields {
		fields[i] = field
	}
	query["fields"] = fields
	data, err := json.Marshal(schema)
	if err != nil {
		b.Fatal(err)
	}
	for _, hit := range []bool{false, true} {
		b.Run(fmt.Sprintf("cached=%t", hit), func(b *testing.B) {
			cache := newDecodedSchemaCache(2)
			if _, err := cache.read(bytes.NewReader(data)); err != nil {
				b.Fatal(err)
			}
			b.ReportAllocs()
			for b.Loop() {
				if !hit {
					_, err = decodeDangSchema(bytes.NewReader(data))
				} else {
					_, err = cache.read(bytes.NewReader(data))
				}
				if err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
