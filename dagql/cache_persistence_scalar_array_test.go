package dagql

import (
	"encoding/json"
	"fmt"
	"math"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestPersistedScalarArrayValuesAndCalls(t *testing.T) {
	ctx := setupPersistCodecTest(t)
	for _, value := range []Typed{
		Array[String]{"", "é\n<>", "escaped\""},
		Array[Int]{math.MinInt64, 9007199254740993, math.MaxInt64},
		Array[Float]{Float(math.Copysign(0, -1)), 1e-300, 1e300},
		Array[Boolean]{true, false},
	} {
		t.Run(value.Type().String(), func(t *testing.T) {
			frame := persistCodecFrame("values", value)
			original, err := NewResultForCall(value, frame)
			require.NoError(t, err)
			encoding, err := DefaultPersistedSelfCodec.EncodeResult(ctx, nil, original)
			require.NoError(t, err)
			for _, srv := range []*Server{nil, CurrentDagqlServer(ctx)} {
				decoded, err := DefaultPersistedSelfCodec.DecodeResult(ctx, srv, 0, frame, encoding.Envelope)
				require.NoError(t, err)
				wantJSON, err := json.Marshal(value)
				require.NoError(t, err)
				gotJSON, err := json.Marshal(decoded.Unwrap())
				require.NoError(t, err)
				require.Equal(t, wantJSON, gotJSON)
				want := original.Unwrap().(Enumerable)
				got := decoded.Unwrap().(Enumerable)
				for i := 1; i <= want.Len(); i++ {
					wantItem, err := want.NthValue(i, frame)
					require.NoError(t, err)
					for _, supplied := range []*ResultCall{nil, cacheTestIntCall("unrelated")} {
						item, err := got.NthValue(i, supplied)
						require.NoError(t, err)
						require.Equal(t, wantItem.Unwrap(), item.Unwrap())
						require.Equal(t, wantItem.cacheSharedResult().loadResultCall(), item.cacheSharedResult().loadResultCall())
					}
				}
				again, err := DefaultPersistedSelfCodec.EncodeResult(ctx, nil, decoded)
				require.NoError(t, err)
				require.Equal(t, encoding, again)
			}
		})
	}
}

func TestPersistedScalarArrayCallIsolationAndAssignment(t *testing.T) {
	ctx := setupPersistCodecTest(t)
	frame := persistCodecFrame("strings", Array[String]{})
	frame.Args = []*ResultCallArg{{Name: "arg", Value: &ResultCallLiteral{Kind: ResultCallLiteralKindString, StringValue: "original"}}}
	original, err := NewResultForCall(Array[String]{"a", "b"}, frame)
	require.NoError(t, err)
	encoding, err := DefaultPersistedSelfCodec.EncodeResult(ctx, nil, original)
	require.NoError(t, err)
	decoded, err := DefaultPersistedSelfCodec.DecodeResult(ctx, nil, 0, frame, encoding.Envelope)
	require.NoError(t, err)
	frame.Field, frame.Args[0].Value.StringValue = "mutated", "mutated"
	list := decoded.Unwrap().(Enumerable)
	first, err := list.NthValue(1, nil)
	require.NoError(t, err)
	first.cacheSharedResult().loadResultCall().Args[0].Value.StringValue = "mutated child"
	second, err := list.NthValue(2, nil)
	require.NoError(t, err)
	require.Equal(t, "strings", second.cacheSharedResult().loadResultCall().Field)
	require.Equal(t, "original", second.cacheSharedResult().loadResultCall().Args[0].Value.StringValue)
	var assigned []string
	require.NoError(t, decoded.Unwrap().(Setter).SetField(reflect.ValueOf(&assigned).Elem()))
	require.Equal(t, []string{"a", "b"}, assigned)
	_, err = list.NthValue(0, nil)
	require.ErrorContains(t, err, "out of bounds")
	_, err = list.NthValue(3, nil)
	require.ErrorContains(t, err, "out of bounds")
}

func TestPersistedInlineScalarArrayRepeatedRestore(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cache.db")
	ctx, cache, srv := persistedListTestCache(t, path)
	value := Array[String]{"one", "two"}
	res := persistedListTestResult(t, ctx, cache, srv, "plain-strings", value)
	id, err := cache.PersistedResultID(res)
	require.NoError(t, err)
	original := persistedListTestEncoding(t, ctx, cache, res)
	for range 2 {
		require.NoError(t, cache.ReleaseSession(ctx, "test-session"))
		require.NoError(t, cache.Close(ctx))
		ctx, cache, srv = persistedListTestCache(t, path)
		res, err = cache.LoadResultByResultID(ctx, "test-session", srv, id)
		require.NoError(t, err)
		list := res.Unwrap().(Enumerable)
		for i, expected := range value {
			item, err := list.NthValue(i+1, nil)
			require.NoError(t, err)
			require.Equal(t, expected, item.Unwrap())
		}
		require.Equal(t, original, persistedListTestEncoding(t, ctx, cache, res))
	}
}

func TestPersistedScalarArrayValidationAndResources(t *testing.T) {
	ctx := setupPersistCodecTest(t)
	frame := persistCodecFrame("strings", Array[String]{})
	item := PersistedResultEnvelope{Version: persistedResultEnvelopeVersion, Kind: persistedResultKindScalar, TypeName: "String", ScalarJSON: json.RawMessage(`"value"`)}
	t.Run("item version remains validated", func(t *testing.T) {
		invalid := item
		invalid.Version--
		env := PersistedResultEnvelope{Version: persistedResultEnvelopeVersion, Kind: persistedResultKindList, Items: []PersistedResultEnvelope{invalid}}
		_, err := DefaultPersistedSelfCodec.DecodeResult(ctx, nil, 0, frame, env)
		require.ErrorContains(t, err, "unsupported version")
	})
	t.Run("invalid scalar keeps its item error", func(t *testing.T) {
		invalid := item
		invalid.ScalarJSON = json.RawMessage(`{"invalid":true}`)
		env := PersistedResultEnvelope{Version: persistedResultEnvelopeVersion, Kind: persistedResultKindList, Items: []PersistedResultEnvelope{item, invalid}}
		_, err := DefaultPersistedSelfCodec.DecodeResult(ctx, nil, 0, frame, env)
		require.ErrorContains(t, err, "decode list item 2: decode scalar_json envelope builtin input")
	})
	t.Run("item resource requirement survives", func(t *testing.T) {
		resource := item
		resource.SessionResourceHandle = "resource-handle"
		env := PersistedResultEnvelope{Version: persistedResultEnvelopeVersion, Kind: persistedResultKindList, Items: []PersistedResultEnvelope{item, resource}}
		decoded, err := DefaultPersistedSelfCodec.DecodeResult(ctx, nil, 0, frame, env)
		require.NoError(t, err)
		child, err := decoded.Unwrap().(Enumerable).NthValue(2, nil)
		require.NoError(t, err)
		require.Equal(t, resource.SessionResourceHandle, child.cacheSharedResult().sessionResourceHandle)
		require.True(t, child.cacheSharedResult().requiredSessionResources.Contains(resource.SessionResourceHandle))
	})
}

func BenchmarkPersistedScalarArrayRestore(b *testing.B) {
	for _, size := range []int{128, 512, 1024} {
		b.Run(fmt.Sprint(size), func(b *testing.B) {
			frame := persistCodecFrame("strings", Array[String]{})
			inputs := make([]*ResultCallLiteral, size)
			env := PersistedResultEnvelope{Version: persistedResultEnvelopeVersion, Kind: persistedResultKindList, TypeName: "String", Items: make([]PersistedResultEnvelope, size)}
			for i := range size {
				inputs[i] = &ResultCallLiteral{Kind: ResultCallLiteralKindString, StringValue: fmt.Sprintf("crate_%04d", i)}
				payload, err := json.Marshal(fmt.Sprintf("digest-%d", i))
				if err != nil {
					b.Fatal(err)
				}
				env.Items[i] = PersistedResultEnvelope{Version: persistedResultEnvelopeVersion, Kind: persistedResultKindScalar, TypeName: "String", ScalarJSON: payload}
			}
			frame.Args = []*ResultCallArg{{Name: "paths", Value: &ResultCallLiteral{Kind: ResultCallLiteralKindList, ListItems: inputs}}}
			var result AnyResult
			b.ReportAllocs()
			for b.Loop() {
				var err error
				result, err = DefaultPersistedSelfCodec.DecodeResult(b.Context(), nil, 0, frame, env)
				if err != nil {
					b.Fatal(err)
				}
			}
			runtime.KeepAlive(result)
		})
	}
}
