package dagql

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"testing"

	"github.com/stretchr/testify/require"
)

func primitiveSelectionServer[T Typed](t testing.TB, values Array[T]) (*Server, context.Context, *Cache) {
	t.Helper()
	srv := newDagqlServerForTest(t, cacheTestQuery{})
	Fields[cacheTestQuery]{
		Func("values", func(context.Context, cacheTestQuery, struct{}) (Array[T], error) {
			return values, nil
		}),
	}.Install(srv)
	ctx := cacheTestContext(t.Context())
	cache, err := NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.CloseDiscardingPersistence()) })
	return srv, ContextWithCache(ctx, cache), cache
}

func checkPrimitiveSelection[T Typed](t *testing.T, values Array[T]) {
	t.Helper()
	srv, ctx, cache := primitiveSelectionServer(t, values)
	original := slices.Clone(values)
	var zero T
	got := Array[T]{zero}
	require.NoError(t, srv.Select(ctx, srv.Root(), &got, Selector{Field: "values"}))
	require.Equal(t, append(Array[T]{zero}, original...), got)
	// Plain values need only the list's cache entry. Each element's call frame
	// is unnecessary when the destination cannot hold a result identity.
	require.Equal(t, 1, cache.Size())
	if len(values) != 0 {
		got[1] = zero
	}
	var again Array[T]
	require.NoError(t, srv.Select(ctx, srv.Root(), &again, Selector{Field: "values"}))
	require.Equal(t, original, again)
	require.Equal(t, original, values, "the destination must not alias cached array storage")
}

func TestSelectPrimitiveArrays(t *testing.T) {
	t.Run("strings", func(t *testing.T) { checkPrimitiveSelection(t, NewStringArray("c", "a", "a")) })
	t.Run("integers", func(t *testing.T) { checkPrimitiveSelection(t, NewIntArray(-3, 1, 1)) })
	t.Run("floats", func(t *testing.T) { checkPrimitiveSelection(t, NewFloatArray(1.25, -2.5, -2.5)) })
	t.Run("booleans", func(t *testing.T) { checkPrimitiveSelection(t, NewBooleanArray(true, false, false)) })
	t.Run("empty", func(t *testing.T) { checkPrimitiveSelection(t, Array[String](nil)) })
}

func TestSelectPrimitiveArrayResultIdentity(t *testing.T) {
	srv, ctx, cache := primitiveSelectionServer(t, NewStringArray("b", "a"))
	var got []AnyResult
	require.NoError(t, srv.Select(ctx, srv.Root(), &got, Selector{Field: "values"}))
	require.Len(t, got, 2)
	for i, value := range got {
		id, err := value.ID()
		require.NoError(t, err)
		loaded, err := srv.LoadType(ctx, id)
		require.NoError(t, err)
		require.Equal(t, []String{"b", "a"}[i], loaded.Unwrap())
	}
	require.Equal(t, 3, cache.Size(), "identity-bearing destinations still materialize their elements")
	var nth String
	require.NoError(t, srv.Select(ctx, srv.Root(), &nth, Selector{Field: "values", Nth: 2}))
	require.Equal(t, String("a"), nth)
	var native []string
	require.NoError(t, srv.Select(ctx, srv.Root(), &native, Selector{Field: "values"}))
	require.Equal(t, []string{"b", "a"}, native, "existing scalar conversion remains available")
}

func TestSelectPrimitiveArrayEvaluation(t *testing.T) {
	srv, ctx, cache := primitiveSelectionServer(t, NewStringArray("unused"))
	calls := 0
	failure := errors.New("discovery failed")
	Fields[cacheTestQuery]{
		Func("current", func(context.Context, cacheTestQuery, struct{}) (Array[String], error) {
			calls++
			if calls == 3 {
				return nil, failure
			}
			return NewStringArray(fmt.Sprint(calls)), nil
		}).WithInput(PerCallInput),
	}.Install(srv)
	for _, want := range []string{"1", "2"} {
		var got Array[String]
		require.NoError(t, srv.Select(ctx, srv.Root(), &got, Selector{Field: "current"}))
		require.Equal(t, NewStringArray(want), got)
	}
	var got Array[String]
	require.ErrorIs(t, srv.Select(ctx, srv.Root(), &got, Selector{Field: "current"}), failure)
	require.Equal(t, 3, calls)
	cacheTestReleaseSession(t, cache, ctx)
	require.ErrorIs(t, srv.Select(ctx, srv.Root(), &got, Selector{Field: "current"}), ErrCacheSessionReleased)
}

func BenchmarkSelectPrimitiveArray(b *testing.B) {
	for _, length := range []int{8, 1024} {
		b.Run(fmt.Sprint(length), func(b *testing.B) {
			values := make(Array[String], length)
			for i := range values {
				values[i] = String(fmt.Sprintf("package/%04d/file.go", i))
			}
			srv, ctx, _ := primitiveSelectionServer(b, values)
			var warm Array[String]
			require.NoError(b, srv.Select(ctx, srv.Root(), &warm, Selector{Field: "values"}))
			b.ReportAllocs()
			b.ResetTimer()
			for range b.N {
				var got Array[String]
				if err := srv.Select(ctx, srv.Root(), &got, Selector{Field: "values"}); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
