package core

import (
	"context"
	"errors"
	"testing"

	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/snapshots/testutil"
	"github.com/stretchr/testify/require"
)

func TestDirectoryWithoutReleasesFailedMutableSnapshot(t *testing.T) {
	for _, tc := range []struct {
		name   string
		cancel bool
	}{
		{name: "mount failure"},
		{name: "canceled mount failure", cancel: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			store := testutil.NewStore(t)
			parent, _ := store.Build(t, nil, "keep.txt", "unchanged")
			mountErr := errors.New("mount failed")
			manager := &withoutFailingManager{SnapshotManager: store.Manager, mountErr: mountErr}
			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()
			if tc.cancel {
				manager.cancel = cancel
			}
			ctx, release, err := bkcache.WithLazyLease(ctx, store.Leases, bkcache.MakeTemporary)
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, release(context.Background())) })
			ctx = ContextWithQuery(ctx, &Query{Server: &cacheVolumeTestQueryServer{cacheManager: manager}})

			var dir Directory
			result, removed, err := dir.withoutPathsFromSnapshot(ctx, parent, "/", "drop")
			require.ErrorIs(t, err, mountErr)
			require.Nil(t, result)
			require.False(t, removed)
			require.NotNil(t, manager.created)
			t.Cleanup(func() { require.NoError(t, manager.created.Release(context.Background())) })

			// Ending the operation lease does not release its mutable Go references.
			// A failed operation must release the reference it cannot return.
			require.NoError(t, release(context.Background()))
			ref, err := store.Manager.GetMutable(t.Context(), manager.created.ID())
			if ref != nil {
				require.NoError(t, ref.Release(context.Background()))
			}
			require.True(t, bkcache.IsNotFound(err), "mutable snapshot should be removed, got %v", err)
			testutil.CheckFile(t, parent, "keep.txt", "unchanged")
		})
	}
}

type withoutFailingManager struct {
	bkcache.SnapshotManager
	created  bkcache.MutableRef
	mountErr error
	cancel   context.CancelFunc
}

func (m *withoutFailingManager) New(ctx context.Context, parent bkcache.ImmutableRef, opts ...bkcache.RefOption) (bkcache.MutableRef, error) {
	ref, err := m.SnapshotManager.New(ctx, parent, opts...)
	if err != nil {
		return nil, err
	}
	m.created = ref
	return &withoutFailingMount{MutableRef: ref, err: m.mountErr, cancel: m.cancel}, nil
}

type withoutFailingMount struct {
	bkcache.MutableRef
	err    error
	cancel context.CancelFunc
}

func (r *withoutFailingMount) Mount(context.Context, bool) (bkcache.MountableRef, error) {
	if r.cancel != nil {
		r.cancel()
	}
	return nil, r.err
}
