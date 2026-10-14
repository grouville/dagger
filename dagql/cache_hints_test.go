package dagql

import (
	"context"
	"fmt"
	"sync"
	"testing"

	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func TestCacheHintSurvivesSessionAndReplacement(t *testing.T) {
	ctx, c, srv := transferTestCache(t)
	child := persistedListTestResult(t, ctx, c, srv, "hint-child", String("snapshot"))
	old := persistedListTestResult(t, ctx, c, srv, "hint-old", &transferTestValue{Text: "old"})
	fresh := persistedListTestResult(t, ctx, c, srv, "hint-new", &transferTestValue{Text: "new"})
	transferTestDependency(c, ctx, old, child)
	oldID := uint64(old.cacheSharedResult().id)
	childID := uint64(child.cacheSharedResult().id)
	freshID := uint64(fresh.cacheSharedResult().id)
	require.NoError(t, c.SaveCacheHint(ctx, "module-a/project", oldID))
	require.NoError(t, c.SaveCacheHint(ctx, "module-b/project", freshID))
	require.NoError(t, c.ReleaseSession(ctx, "test-session"))
	_, err := c.Prune(ctx, []CachePrunePolicy{{All: true}})
	require.NoError(t, err)

	readerCtx := engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{ClientID: "hint-reader", SessionID: "hint-reader"})
	loaded, err := c.LoadCacheHint(readerCtx, "module-a/project", "hint-reader", srv)
	require.NoError(t, err)
	require.Equal(t, oldID, uint64(loaded.cacheSharedResult().id))
	other, err := c.LoadCacheHint(readerCtx, "module-b/project", "hint-reader", srv)
	require.NoError(t, err)
	require.Equal(t, freshID, uint64(other.cacheSharedResult().id))
	missing, err := c.LoadCacheHint(ctx, "module-c/project", "", srv)
	require.NoError(t, err)
	require.Nil(t, missing)
	require.NoError(t, c.ReleaseSession(readerCtx, "hint-reader"))

	require.NoError(t, c.SaveCacheHint(ctx, "module-a/project", freshID))
	c.egraphMu.RLock()
	_, oldKept := c.resultsByID[sharedResultID(oldID)]
	_, childKept := c.resultsByID[sharedResultID(childID)]
	c.egraphMu.RUnlock()
	require.False(t, oldKept, "replacement releases the old native result")
	require.False(t, childKept, "replacement releases the old snapshot closure")
}

func TestCacheHintInvalidPublicationKeepsPrevious(t *testing.T) {
	ctx, c, srv := transferTestCache(t)
	res := persistedListTestResult(t, ctx, c, srv, "hint-valid", &transferTestValue{Text: "valid"})
	number := uint64(res.cacheSharedResult().id)
	require.NoError(t, c.SaveCacheHint(ctx, "project", number))
	require.ErrorIs(t, c.SaveCacheHint(ctx, "project", 9999999), ErrUnknownEntry)
	canceled, cancel := context.WithCancel(ctx)
	cancel()
	require.ErrorIs(t, c.SaveCacheHint(canceled, "project", number), context.Canceled)
	loaded, err := c.LoadCacheHint(ctx, "project", "test-session", srv)
	require.NoError(t, err)
	require.Equal(t, number, uint64(loaded.cacheSharedResult().id))
}

func TestCacheHintEvictionAndCloseReleaseHolds(t *testing.T) {
	ctx, c, srv := transferTestCache(t)
	first := persistedListTestResult(t, ctx, c, srv, "hint-first", &transferTestValue{Text: "first"})
	other := persistedListTestResult(t, ctx, c, srv, "hint-other", &transferTestValue{Text: "other"})
	firstID := uint64(first.cacheSharedResult().id)
	otherID := uint64(other.cacheSharedResult().id)
	require.NoError(t, c.SaveCacheHint(ctx, "first", firstID))
	for i := range maxCacheHints - 1 {
		require.NoError(t, c.SaveCacheHint(ctx, fmt.Sprint(i), otherID))
	}
	require.NoError(t, c.ReleaseSession(ctx, "test-session"))
	_, err := c.Prune(ctx, []CachePrunePolicy{{All: true}})
	require.NoError(t, err)
	require.NoError(t, c.SaveCacheHint(ctx, "overflow", otherID))
	missing, err := c.LoadCacheHint(ctx, "first", "", srv)
	require.NoError(t, err)
	require.Nil(t, missing)
	c.egraphMu.RLock()
	_, firstKept := c.resultsByID[sharedResultID(firstID)]
	c.egraphMu.RUnlock()
	require.False(t, firstKept, "bounded eviction releases the native result")
	require.NoError(t, c.CloseDiscardingPersistence())
	c.egraphMu.RLock()
	_, otherKept := c.resultsByID[sharedResultID(otherID)]
	c.egraphMu.RUnlock()
	require.False(t, otherKept, "shutdown releases every index hold")
	require.ErrorIs(t, c.SaveCacheHint(ctx, "after-close", otherID), ErrCacheClosed)
	_, err = c.LoadCacheHint(ctx, "after-close", "", srv)
	require.ErrorIs(t, err, ErrCacheClosed)
}

func TestCacheHintConcurrentReplacementAndRead(t *testing.T) {
	ctx, c, srv := transferTestCache(t)
	old := persistedListTestResult(t, ctx, c, srv, "hint-concurrent-old", &transferTestValue{Text: "old"})
	fresh := persistedListTestResult(t, ctx, c, srv, "hint-concurrent-new", &transferTestValue{Text: "new"})
	oldID := uint64(old.cacheSharedResult().id)
	freshID := uint64(fresh.cacheSharedResult().id)
	require.NoError(t, c.SaveCacheHint(ctx, "project", oldID))
	var wg sync.WaitGroup
	errs := make(chan error, 400)
	for worker := range 4 {
		wg.Go(func() {
			for i := range 100 {
				number := oldID
				if (worker+i)%2 == 0 {
					number = freshID
				}
				if err := c.SaveCacheHint(ctx, "project", number); err != nil {
					errs <- err
					continue
				}
				res, err := c.LoadCacheHint(ctx, "project", "test-session", srv)
				if err != nil {
					errs <- err
				} else if res == nil {
					errs <- fmt.Errorf("lost a concurrently replaced hint")
				}
			}
		})
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		require.NoError(t, err)
	}
}
