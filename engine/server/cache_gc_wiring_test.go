package server

import (
	"context"
	"sync/atomic"
	"testing"

	ctdmetadata "github.com/containerd/containerd/v2/core/metadata"
	"github.com/containerd/containerd/v2/pkg/gc"
	localcontentstore "github.com/containerd/containerd/v2/plugins/content/local"
	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine/config"
	bkconfig "github.com/dagger/dagger/internal/buildkit/cmd/buildkitd/config"
	"github.com/stretchr/testify/require"
)

// Observe real containerd collections without adding collectible resources.
type gcCollectionCounter struct{ calls atomic.Int32 }

func (c *gcCollectionCounter) ReferenceLabel() string { return "dagger.test.collection-counter" }
func (c *gcCollectionCounter) StartCollection(context.Context) (ctdmetadata.CollectionContext, error) {
	c.calls.Add(1)
	return gcEmptyCollection{}, nil
}

type gcEmptyCollection struct{}

func (gcEmptyCollection) All(func(gc.Node))                    {}
func (gcEmptyCollection) Active(string, func(gc.Node))         {}
func (gcEmptyCollection) Leased(string, string, func(gc.Node)) {}
func (gcEmptyCollection) Remove(gc.Node)                       {}
func (gcEmptyCollection) Cancel() error                        { return nil }
func (gcEmptyCollection) Finish() error                        { return nil }

func newGCWiringTestServer(t testing.TB) *Server {
	t.Helper()
	srv := &Server{rootDir: t.TempDir()}
	require.NoError(t, srv.initRootPaths())
	builtin, err := localcontentstore.NewStore(t.TempDir())
	require.NoError(t, err)
	srv.builtinContentStore = builtin
	reset, err := srv.initLocalCacheStateOnce(t.Context(), config.Config{}, bkconfig.OCIConfig{})
	require.NoError(t, err)
	require.Equal(t, localCacheStateResetNone, reset)
	t.Cleanup(func() { require.NoError(t, srv.closeLocalCacheStateForReset()) })
	require.NoError(t, srv.snapshotGarbage.CollectIfPending(t.Context()))
	return srv
}

func TestLocalCacheMetadataPruneDoesNotCollectSnapshots(t *testing.T) {
	for _, mode := range []string{"scheduled", "explicit"} {
		t.Run(mode, func(t *testing.T) {
			// Use the production initializer: a cache constructed with a nil
			// collector here would miss an incorrectly installed callback.
			srv := newGCWiringTestServer(t)
			counter := &gcCollectionCounter{}
			srv.containerdMetaDB.RegisterCollectibleResource(gc.ResourceMax-1, counter)

			ctx := addGCTestPersistable(t, srv.engineCache, "metadata-only", "metadataOnly", dagql.NewInt(1))
			require.NoError(t, srv.engineCache.ReleaseSession(ctx, "metadata-only"))
			require.False(t, srv.snapshotGarbage.pending.Load())
			maximum := srv.engineCache.MetadataEstimate().EstimatedBytes - 1
			target := int64(1)
			if mode == "scheduled" {
				srv.workerGCPolicies = nil
				srv.localCacheGCEnabled = true
				srv.dagqlCacheMaxEstimatedBytes = maximum
				srv.dagqlCacheTargetEstimatedBytes = target
				require.NoError(t, srv.gcLocked(t.Context(), localCacheGCScheduled))
			} else {
				_, err := srv.PruneEngineLocalCacheEntries(t.Context(), core.EngineCachePruneOptions{
					MaxEstimatedBytes: &maximum, TargetEstimatedBytes: &target,
				})
				require.NoError(t, err)
			}
			require.Zero(t, srv.engineCache.EntryStats().RetainedCalls, "the scalar must actually be pruned")
			require.Zero(t, counter.calls.Load(), "metadata-only eviction releases no snapshot lease")
		})
	}
}
