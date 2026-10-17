package dangv2

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"io"
	"slices"

	lru "github.com/hashicorp/golang-lru/v2"
	"github.com/vito/dang/v2/pkg/introspection"
	"golang.org/x/sync/singleflight"
)

// Retain at most eight decoded schemas, each with at most 1 MiB of JSON input.
// The cache contains only schema data, never clients or engine resources.
const maxCachedSchemaBytes = 1 << 20

var dangSchemas = newDecodedSchemaCache(8)

type decodedSchemaCache struct {
	entries  *lru.Cache[[sha256.Size]byte, *introspection.Schema]
	decoding singleflight.Group
}

func newDecodedSchemaCache(entries int) *decodedSchemaCache {
	cache, err := lru.New[[sha256.Size]byte, *introspection.Schema](entries)
	if err != nil {
		panic(err)
	}
	return &decodedSchemaCache{entries: cache}
}

func (cache *decodedSchemaCache) read(reader io.Reader) (*introspection.Schema, error) {
	data, err := io.ReadAll(io.LimitReader(reader, maxCachedSchemaBytes+1))
	if err != nil {
		return nil, err
	}
	if len(data) > maxCachedSchemaBytes {
		return decodeDangSchema(io.MultiReader(bytes.NewReader(data), reader))
	}
	key := sha256.Sum256(data)
	if schema, ok := cache.entries.Get(key); ok {
		return cloneDecodedSchema(schema), nil
	}
	// A concurrent first use decodes once. Each caller receives its own copy.
	value, err, _ := cache.decoding.Do(string(key[:]), func() (any, error) {
		if schema, ok := cache.entries.Get(key); ok {
			return schema, nil
		}
		schema, err := decodeDangSchema(bytes.NewReader(data))
		if err != nil {
			return nil, err
		}
		cache.entries.Add(key, schema)
		return schema, nil
	})
	if err != nil {
		return nil, err
	}
	return cloneDecodedSchema(value.(*introspection.Schema)), nil
}

func decodeDangSchema(reader io.Reader) (*introspection.Schema, error) {
	var response introspection.Response
	if err := json.NewDecoder(reader).Decode(&response); err != nil {
		return nil, err
	}
	return response.Schema, nil
}

// cloneDecodedSchema copies the JSON-decoded tree before a caller mutates it.
// ParentObject is not serialized and is nil in this tree.
func cloneDecodedSchema(s *introspection.Schema) *introspection.Schema {
	if s == nil {
		return nil
	}
	out := *s
	out.MutationType = clonePointer(s.MutationType)
	out.SubscriptionType = clonePointer(s.SubscriptionType)
	out.Types = cloneItems(s.Types, cloneSchemaType)
	out.Directives = cloneItems(s.Directives, func(d *introspection.DirectiveDef) *introspection.DirectiveDef {
		if d == nil {
			return nil
		}
		c := *d
		c.Locations = slices.Clone(d.Locations)
		c.Args = cloneItems(d.Args, cloneInputValue)
		return &c
	})
	return &out
}

func cloneSchemaType(t *introspection.Type) *introspection.Type {
	if t == nil {
		return nil
	}
	out := *t
	out.Fields = cloneItems(t.Fields, func(f *introspection.Field) *introspection.Field {
		if f == nil {
			return nil
		}
		c := *f
		c.TypeRef = cloneTypeRef(f.TypeRef)
		c.Args = cloneItems(f.Args, cloneInputValue)
		c.Directives = cloneDirectives(f.Directives)
		c.ParentObject = nil
		return &c
	})
	out.InputFields = cloneItems(t.InputFields, cloneInputValue)
	out.EnumValues = cloneItems(t.EnumValues, func(e introspection.EnumValue) introspection.EnumValue {
		e.Directives = cloneDirectives(e.Directives)
		return e
	})
	out.Interfaces = cloneItems(t.Interfaces, cloneSchemaType)
	out.PossibleTypes = cloneItems(t.PossibleTypes, cloneSchemaType)
	out.Directives = cloneDirectives(t.Directives)
	return &out
}

func cloneTypeRef(t *introspection.TypeRef) *introspection.TypeRef {
	if t == nil {
		return nil
	}
	out := *t
	out.OfType = cloneTypeRef(t.OfType)
	return &out
}

func cloneInputValue(i introspection.InputValue) introspection.InputValue {
	i.DefaultValue = clonePointer(i.DefaultValue)
	i.TypeRef = cloneTypeRef(i.TypeRef)
	i.Directives = cloneDirectives(i.Directives)
	return i
}

func cloneDirectives(ds introspection.Directives) introspection.Directives {
	return cloneItems(ds, func(d *introspection.Directive) *introspection.Directive {
		if d == nil {
			return nil
		}
		out := *d
		out.Args = cloneItems(d.Args, func(a *introspection.DirectiveArg) *introspection.DirectiveArg {
			if a == nil {
				return nil
			}
			c := *a
			c.Value = clonePointer(a.Value)
			return &c
		})
		return &out
	})
}

func clonePointer[T any](p *T) *T {
	if p == nil {
		return nil
	}
	out := *p
	return &out
}

func cloneItems[S ~[]T, T any](items S, clone func(T) T) S {
	if items == nil {
		return nil
	}
	out := make(S, len(items))
	for i, item := range items {
		out[i] = clone(item)
	}
	return out
}
