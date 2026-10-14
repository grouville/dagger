package dagql

import (
	"context"
	"fmt"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCacheHintSurvivesRestart(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cache.db")
	ctx, cache, srv := persistedListTestCache(t, path)
	first := persistedListTestResult(t, ctx, cache, srv, "first-hint", String("first"))
	frame := &ResultCall{Kind: ResultCallKindField, Field: "latest-hint", Type: NewResultCallType(String("").Type())}
	latest, err := cache.GetOrInitCall(ctx, "test-session", srv, &CallRequest{ResultCall: frame}, func(context.Context) (AnyResult, error) {
		return NewResultForCall(String("latest"), frame)
	})
	require.NoError(t, err)
	firstID, err := cache.PersistedResultID(first)
	require.NoError(t, err)
	latestID, err := cache.PersistedResultID(latest)
	require.NoError(t, err)
	require.NoError(t, cache.SaveCacheHint(ctx, "module-a/project", firstID))
	require.NoError(t, cache.SaveCacheHint(ctx, "module-a/project", latestID))
	require.NoError(t, cache.SaveCacheHint(ctx, "module-b/project", firstID))
	for range 2 {
		require.NoError(t, cache.ReleaseSession(ctx, "test-session"))
		require.NoError(t, cache.Close(ctx))
		ctx, cache, srv = persistedListTestCache(t, path)
		loaded, err := cache.LoadCacheHint(ctx, "module-a/project", "test-session", srv)
		require.NoError(t, err)
		require.NotNil(t, loaded)
		require.Equal(t, String("latest"), loaded.Unwrap())
		other, err := cache.LoadCacheHint(ctx, "module-b/project", "test-session", srv)
		require.NoError(t, err)
		require.NotNil(t, other)
		require.Equal(t, String("first"), other.Unwrap())
		missing, err := cache.LoadCacheHint(ctx, "module-c/project", "test-session", srv)
		require.NoError(t, err)
		require.Nil(t, missing)
	}
}

func TestCacheHintRestoredValueCanBePruned(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cache.db")
	ctx, cache, srv := persistedListTestCache(t, path)
	value := persistedListTestResult(t, ctx, cache, srv, "prunable-hint", String("value"))
	number, err := cache.PersistedResultID(value)
	require.NoError(t, err)
	require.NoError(t, cache.SaveCacheHint(ctx, "project", number))
	require.NoError(t, cache.ReleaseSession(ctx, "test-session"))
	require.NoError(t, cache.Close(ctx))
	ctx, cache, srv = persistedListTestCache(t, path)
	_, err = cache.Prune(ctx, []CachePrunePolicy{{All: true}})
	require.NoError(t, err)
	missing, err := cache.LoadCacheHint(ctx, "project", "test-session", srv)
	require.NoError(t, err)
	require.Nil(t, missing, "pruning an unused restored hint is an acceleration miss")
}

func TestCacheHintRestoresBoundedLRU(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cache.db")
	ctx, cache, srv := persistedListTestCache(t, path)
	value := persistedListTestResult(t, ctx, cache, srv, "bounded-hint", String("value"))
	number, err := cache.PersistedResultID(value)
	require.NoError(t, err)
	for i := range maxCacheHints {
		require.NoError(t, cache.SaveCacheHint(ctx, fmt.Sprint(i), number))
	}
	_, err = cache.LoadCacheHint(ctx, "0", "test-session", srv)
	require.NoError(t, err)
	require.NoError(t, cache.ReleaseSession(ctx, "test-session"))
	require.NoError(t, cache.Close(ctx))
	ctx, cache, srv = persistedListTestCache(t, path)
	require.Len(t, cache.cacheHints.entries, maxCacheHints)
	require.NoError(t, cache.SaveCacheHint(ctx, "overflow", number))
	missing, err := cache.LoadCacheHint(ctx, "1", "test-session", srv)
	require.NoError(t, err)
	require.Nil(t, missing)
	kept, err := cache.LoadCacheHint(ctx, "0", "test-session", srv)
	require.NoError(t, err)
	require.NotNil(t, kept)
}

func TestCacheHintDoesNotPersistSessionResource(t *testing.T) {
	path := filepath.Join(t.TempDir(), "cache.db")
	ctx, cache, srv := persistedListTestCache(t, path)
	handle := cacheTestVolatileSessionResourceHandle("hint-secret")
	require.NoError(t, cache.BindSessionResource(ctx, "test-session", "dagql-test-client", handle, "bound"))
	frame := &ResultCall{Kind: ResultCallKindField, Field: "resource-hint", Type: NewResultCallType(String("").Type())}
	value, err := cache.GetOrInitCall(ctx, "test-session", srv, &CallRequest{ResultCall: frame}, func(ctx context.Context) (AnyResult, error) {
		res, err := NewResultForCall(String("secret"), frame)
		if err != nil {
			return nil, err
		}
		return res.WithSessionResourceHandleAny(ctx, handle)
	})
	require.NoError(t, err)
	number, err := cache.PersistedResultID(value)
	require.NoError(t, err)
	require.NoError(t, cache.SaveCacheHint(ctx, "project", number))
	require.NoError(t, cache.ReleaseSession(ctx, "test-session"))
	require.NoError(t, cache.Close(ctx))
	ctx, cache, srv = persistedListTestCache(t, path)
	missing, err := cache.LoadCacheHint(ctx, "project", "test-session", srv)
	require.NoError(t, err)
	require.Nil(t, missing)
}
