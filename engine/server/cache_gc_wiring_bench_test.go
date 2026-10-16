package server

import (
	"context"
	"fmt"
	"testing"

	"github.com/containerd/containerd/v2/core/leases"
	ctdmetadata "github.com/containerd/containerd/v2/core/metadata"
	"github.com/containerd/containerd/v2/pkg/gc"
	"github.com/containerd/containerd/v2/pkg/namespaces"
	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func BenchmarkLocalCacheMetadataPrune(b *testing.B) {
	for _, snapshots := range []int{0, 1000} {
		b.Run(fmt.Sprintf("snapshots=%d", snapshots), func(b *testing.B) {
			srv := newGCWiringTestServer(b)
			ctx := namespaces.WithNamespace(b.Context(), "dagger")
			lm := ctdmetadata.NewLeaseManager(srv.containerdMetaDB)
			owner, err := lm.Create(ctx, leases.WithID("retained"))
			require.NoError(b, err)
			ss := srv.containerdMetaDB.Snapshotter(srv.snapshotterName)
			for i := range snapshots {
				active, committed := fmt.Sprintf("active-%d", i), fmt.Sprintf("retained-%d", i)
				_, err := ss.Prepare(ctx, active, "")
				require.NoError(b, err)
				require.NoError(b, ss.Commit(ctx, committed, active))
				require.NoError(b, lm.AddResource(ctx, owner, leases.Resource{
					ID: committed, Type: "snapshots/" + srv.snapshotterName,
				}))
			}
			require.NoError(b, srv.snapshotGarbage.Collect(ctx))
			counter := &gcCollectionCounter{}
			srv.containerdMetaDB.RegisterCollectibleResource(gc.ResourceMax-1, counter)
			b.ReportAllocs()
			b.ResetTimer()
			for i := range b.N {
				b.StopTimer()
				sessionID := fmt.Sprintf("metadata-%d", i)
				sessionCtx := engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{
					ClientID: sessionID, SessionID: sessionID,
				})
				frame := &dagql.ResultCall{
					Kind: dagql.ResultCallKindField, Type: dagql.NewResultCallType(dagql.NewInt(1).Type()), Field: "metadataOnly",
				}
				_, err := srv.engineCache.GetOrInitCall(sessionCtx, sessionID, gcTestTypeResolver{}, &dagql.CallRequest{
					ResultCall: frame, IsPersistable: true,
				}, func(context.Context) (dagql.AnyResult, error) {
					return dagql.NewResultForCall(dagql.NewInt(1), frame)
				})
				require.NoError(b, err)
				require.NoError(b, srv.engineCache.ReleaseSession(sessionCtx, sessionID))
				maximum, target := srv.engineCache.MetadataEstimate().EstimatedBytes-1, int64(1)
				b.StartTimer()
				_, err = srv.PruneEngineLocalCacheEntries(ctx, core.EngineCachePruneOptions{
					MaxEstimatedBytes: &maximum, TargetEstimatedBytes: &target,
				})
				b.StopTimer()
				require.NoError(b, err)
				require.Zero(b, srv.engineCache.EntryStats().RetainedCalls)
				b.StartTimer()
			}
			b.StopTimer()
			b.ReportMetric(float64(counter.calls.Load())/float64(b.N), "collections/op")
			resources, err := lm.ListResources(ctx, owner)
			require.NoError(b, err)
			require.Len(b, resources, snapshots)
			for i := range snapshots {
				_, err := ss.Stat(ctx, fmt.Sprintf("retained-%d", i))
				require.NoError(b, err)
			}
		})
	}
}
