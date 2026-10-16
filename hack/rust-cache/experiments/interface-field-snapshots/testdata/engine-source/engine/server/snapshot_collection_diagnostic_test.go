package server

import (
	"context"
	"testing"

	"github.com/dagger/dagger/engine/snapshots/testutil"
	"github.com/stretchr/testify/require"
)

func TestSnapshotCollectionDiagnosticPreservesPending(t *testing.T) {
	// A nil DB proves a deferred request never touches containerd.
	garbage := &snapshotGarbage{}
	garbage.deferred.Store(true)
	require.NoError(t, garbage.Collect(context.Background()))
	require.True(t, garbage.pending.Load())
	require.True(t, garbage.diagnosticState()["deferred"].(bool))
}

func TestSnapshotCollectionDiagnosticDrainPreservesLeasedSnapshot(t *testing.T) {
	store := testutil.NewStore(t)
	ctx := context.Background()
	garbage := newSnapshotGarbage(store.DB)
	kept, _ := store.Build(t, nil, "kept", "kept data")
	released, owner := store.Build(t, nil, "released", "released data")
	id := released.SnapshotID()
	require.NoError(t, released.Release(ctx))
	require.NoError(t, store.Manager.RemoveLease(ctx, owner))
	garbage.deferred.Store(true)
	require.NoError(t, garbage.CollectIfPending(ctx))
	requireSnapshotExists(t, store, id)
	require.True(t, garbage.pending.Load())
	garbage.deferred.Store(false)
	require.NoError(t, garbage.CollectIfPending(ctx))
	requireSnapshotCollected(t, store, id)
	testutil.CheckFile(t, kept, "kept", "kept data")
}
