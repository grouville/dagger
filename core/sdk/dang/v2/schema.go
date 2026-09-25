package dangv2

import (
	"context"
	"encoding/json"
	"fmt"
	"slices"
	"strconv"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/engine/wcprof"
	"github.com/vito/dang/v2/pkg/introspection"
)

func loadDangSchema(ctx context.Context, file dagql.Result[*core.File]) (*introspection.Response, error) {
	decode := func(ctx context.Context) (*introspection.Response, error) {
		f, err := file.Self().Open(ctx, dagql.ObjectResult[*core.File]{Result: file})
		if err != nil {
			return nil, fmt.Errorf("open schema file: %w", err)
		}
		defer f.Close()
		_, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "dang.decodeSchema", wcprof.OpOpts{})
		var intro introspection.Response
		err = json.NewDecoder(f).Decode(&intro)
		op.EndErr(err)
		if err != nil {
			return nil, fmt.Errorf("decode schema: %w", err)
		}
		return &intro, nil
	}
	cache, err := dagql.EngineCache(ctx)
	if err != nil {
		return decode(ctx)
	}
	id, err := file.ID()
	if err != nil {
		return decode(ctx)
	}
	md, err := engine.ClientMetadataFromContext(ctx)
	if err != nil {
		return nil, err
	}
	return cachedDangSchema(ctx, cache, md.SessionID, id.EngineResultID(), decode)
}

// Cache only decoded data, never an evaluator, inferred type or GraphQL client.
// The caller already holds the schema File; its engine-unique result ID keeps
// different views/hidden fields/schema contents separate. The session owns the
// arbitrary cache entry, so no parsed schema survives through this cache into
// another command. Copy before Dang adds self types or sorts/mutates fields.
func cachedDangSchema(ctx context.Context, cache *dagql.Cache, sessionID string, fileID uint64, decode func(context.Context) (*introspection.Response, error)) (*introspection.Response, error) {
	key := "dang.schema:" + sessionID + ":" + strconv.FormatUint(fileID, 10)
	res, err := cache.GetOrInitArbitrary(ctx, sessionID, key, func(ctx context.Context) (any, error) {
		return decode(ctx)
	})
	if err != nil {
		return nil, err
	}
	intro, ok := res.Value().(*introspection.Response)
	if !ok {
		return nil, fmt.Errorf("unexpected Dang schema cache value %T", res.Value())
	}
	_, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "dang.cloneSchema", wcprof.OpOpts{Ident: strconv.FormatUint(fileID, 10)})
	copy := cloneSchemaValue(intro)
	copy.Schema = cloneIntrospectionSchema(intro.Schema)
	op.End(wcprof.OutcomeOK)
	return copy, nil
}

// These clones operate on freshly decoded JSON trees, before runtime visitors
// can add parent links. Strings are immutable and can be shared; every mutable
// pointer/slice is copied. In particular a field's ParentObject starts nil.
func cloneIntrospectionSchema(src *introspection.Schema) *introspection.Schema {
	if src == nil {
		return nil
	}
	dst := *src
	dst.MutationType = cloneSchemaValue(src.MutationType)
	dst.SubscriptionType = cloneSchemaValue(src.SubscriptionType)
	dst.Types = cloneSchemaSlice(src.Types, cloneIntrospectionType)
	dst.Directives = cloneSchemaSlice(src.Directives, func(src *introspection.DirectiveDef) *introspection.DirectiveDef {
		if src == nil {
			return nil
		}
		dst := *src
		dst.Locations = slices.Clone(src.Locations)
		dst.Args = cloneSchemaSlice(src.Args, cloneIntrospectionInput)
		return &dst
	})
	return &dst
}

func cloneIntrospectionType(src *introspection.Type) *introspection.Type {
	if src == nil {
		return nil
	}
	dst := *src
	dst.Fields = cloneSchemaSlice(src.Fields, func(src *introspection.Field) *introspection.Field {
		if src == nil {
			return nil
		}
		dst := *src
		dst.TypeRef = cloneIntrospectionTypeRef(src.TypeRef)
		dst.Args = cloneSchemaSlice(src.Args, cloneIntrospectionInput)
		dst.Directives = cloneIntrospectionDirectives(src.Directives)
		dst.ParentObject = nil
		return &dst
	})
	dst.InputFields = cloneSchemaSlice(src.InputFields, cloneIntrospectionInput)
	dst.EnumValues = cloneSchemaSlice(src.EnumValues, func(src introspection.EnumValue) introspection.EnumValue {
		src.Directives = cloneIntrospectionDirectives(src.Directives)
		return src
	})
	dst.Interfaces = cloneSchemaSlice(src.Interfaces, cloneIntrospectionType)
	dst.PossibleTypes = cloneSchemaSlice(src.PossibleTypes, cloneIntrospectionType)
	dst.Directives = cloneIntrospectionDirectives(src.Directives)
	return &dst
}

func cloneIntrospectionInput(src introspection.InputValue) introspection.InputValue {
	src.DefaultValue = cloneSchemaValue(src.DefaultValue)
	src.TypeRef = cloneIntrospectionTypeRef(src.TypeRef)
	src.Directives = cloneIntrospectionDirectives(src.Directives)
	return src
}

func cloneIntrospectionTypeRef(src *introspection.TypeRef) *introspection.TypeRef {
	if src == nil {
		return nil
	}
	dst := *src
	dst.OfType = cloneIntrospectionTypeRef(src.OfType)
	return &dst
}

func cloneIntrospectionDirectives(src introspection.Directives) introspection.Directives {
	return cloneSchemaSlice(src, func(src *introspection.Directive) *introspection.Directive {
		if src == nil {
			return nil
		}
		dst := *src
		dst.Args = cloneSchemaSlice(src.Args, func(src *introspection.DirectiveArg) *introspection.DirectiveArg {
			if src == nil {
				return nil
			}
			dst := *src
			dst.Value = cloneSchemaValue(src.Value)
			return &dst
		})
		return &dst
	})
}

func cloneSchemaValue[T any](src *T) *T {
	if src == nil {
		return nil
	}
	dst := *src
	return &dst
}

func cloneSchemaSlice[S ~[]T, T any](src S, clone func(T) T) S {
	if src == nil {
		return nil
	}
	dst := make(S, len(src))
	for i, value := range src {
		dst[i] = clone(value)
	}
	return dst
}
