package dagql

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func scalarArrayTestServer(t *testing.T) (context.Context, *Cache, *Server) {
	t.Helper()
	ctx := cacheTestContext(t.Context())
	cache, err := NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.CloseDiscardingPersistence()) })
	ctx = ContextWithCache(ctx, cache)
	srv := cacheTestServer(t)
	Fields[cacheTestQuery]{
		Func("strings", func(context.Context, cacheTestQuery, struct{}) (Array[String], error) {
			return NewStringArray("", "hello", "\u00e9\n\""), nil
		}),
		Func("ints", func(context.Context, cacheTestQuery, struct{}) (Array[Int], error) {
			return NewIntArray(-3, 0, 42), nil
		}),
		Func("floats", func(context.Context, cacheTestQuery, struct{}) (Array[Float], error) {
			return NewFloatArray(-1.25, 0.0, 3.5), nil
		}),
		Func("bools", func(context.Context, cacheTestQuery, struct{}) (Array[Boolean], error) {
			return NewBoolArray(true, false), nil
		}),
		Func("empty", func(context.Context, cacheTestQuery, struct{}) (Array[String], error) {
			return nil, nil
		}),
	}.Install(srv)
	return srvToContext(ctx, srv), cache, srv
}

func TestPrimitiveArrayResponseAndExplicitNth(t *testing.T) {
	ctx, _, srv := scalarArrayTestServer(t)
	result, err := srv.Query(ctx, `{strings ints floats bools empty}`, nil)
	require.NoError(t, err)
	data, err := json.Marshal(result)
	require.NoError(t, err)
	require.JSONEq(t, `{"strings":["","hello","\u00e9\n\""],"ints":[-3,0,42],"floats":[-1.25,0,3.5],"bools":[true,false],"empty":[]}`, string(data))

	list, err := srv.Root().Select(ctx, srv, Selector{Field: "strings"})
	require.NoError(t, err)
	first, err := list.NthValue(ctx, 2)
	require.NoError(t, err)
	second, err := list.NthValue(ctx, 2)
	require.NoError(t, err)
	require.Equal(t, String("hello"), first.Unwrap())
	require.NotZero(t, first.cacheSharedResult().id)
	require.Equal(t, first.cacheSharedResult().id, second.cacheSharedResult().id)
}

func TestPrimitiveArrayResponseRequiresLiveBoundSession(t *testing.T) {
	ctx, cache, srv := scalarArrayTestServer(t)
	list, err := srv.Root().Select(ctx, srv, Selector{Field: "strings"})
	require.NoError(t, err)
	values := list.Unwrap().(Array[String])
	handle := cacheTestVolatileSessionResourceHandle("PRIMITIVE_ARRAY_OUTPUT")
	require.NoError(t, cache.BindSessionResource(ctx, "test-session", "dagql-test-client", handle, "bound"))
	currentEntryTestRequireHandle(t, ctx, cache, srv, "test-session", list, handle)
	_, err = primitiveArrayOutput(cacheTestSessionContext(ctx, "unbound"), list, values)
	require.ErrorContains(t, err, "has not bound")
	_, err = primitiveArrayOutput(ctx, list, values)
	require.NoError(t, err)
	canceled, cancel := context.WithCancel(ctx)
	cancel()
	_, err = primitiveArrayOutput(canceled, list, values)
	require.ErrorIs(t, err, context.Canceled)
	require.NoError(t, cache.ReleaseSession(ctx, "test-session"))
	_, err = primitiveArrayOutput(ctx, list, values)
	require.ErrorIs(t, err, ErrCacheSessionReleased)
}

func TestPrimitiveArrayResponseRefusesReleasedSessionAtExit(t *testing.T) {
	ctx, cache, srv := scalarArrayTestServer(t)
	list, err := srv.Root().Select(ctx, srv, Selector{Field: "strings"})
	require.NoError(t, err)
	atExit, allowExit := make(chan struct{}), make(chan struct{})
	cache.testBeforeSessionOperationExit = func(session string) {
		if session == "test-session" {
			close(atExit)
			<-allowExit
		}
	}
	type response struct {
		value []any
		err   error
	}
	done := make(chan response, 1)
	go func() {
		value, err := primitiveArrayOutput(ctx, list, list.Unwrap().(Array[String]))
		done <- response{value, err}
	}()
	<-atExit
	require.NoError(t, cache.ReleaseSession(ctx, "test-session"))
	close(allowExit)
	got := <-done
	require.ErrorIs(t, got.err, ErrCacheSessionReleased)
	require.Nil(t, got.value)
}
