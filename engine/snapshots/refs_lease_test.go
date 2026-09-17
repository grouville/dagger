package snapshots

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/mount"
	ctdsnapshots "github.com/containerd/containerd/v2/core/snapshots"
	"github.com/stretchr/testify/require"
)

// Exercise the real immutableRef.Mount, including its lease option ordering
// and release wrapper. Persistent containerd GC/restart is a separate test gate.
func TestImmutableMountLeaseExpiration(t *testing.T) {
	for _, tc := range []struct {
		name     string
		bounded  bool
		ttl      time.Duration
		viewErr  bool
		mountErr bool
	}{
		{name: "ordinary mount unchanged"},
		{name: "bounded view", bounded: true, ttl: time.Hour},
		{name: "view failure", bounded: true, ttl: time.Hour, viewErr: true},
		{name: "mount failure", bounded: true, ttl: time.Hour, mountErr: true},
		{name: "zero rejected", bounded: true},
		{name: "negative rejected", bounded: true, ttl: -time.Second},
	} {
		t.Run(tc.name, func(t *testing.T) {
			cm := newApplySnapshotDiffTestManager(t)
			ref := addApplySnapshotDiffTestImmutable(t, cm, "result")
			lm := cm.LeaseManager
			caller, ctx, err := NewLease(context.Background(), lm, MakeTemporary)
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, caller.Discard()) })
			if tc.bounded {
				ctx = WithMountLeaseExpiration(ctx, tc.ttl)
			}
			injected := errors.New("injected mount failure")
			calledView := false
			before := time.Now()
			cm.Snapshotter = &immutableMountLeaseTestSnapshotter{
				MergeSnapshotter: cm.Snapshotter,
				view: func(ctx context.Context, key, parent string) (MountableRef, error) {
					calledView = true
					require.Equal(t, ref.SnapshotID(), parent)
					all, err := lm.List(ctx)
					require.NoError(t, err)
					require.Len(t, all, 2, "view must own a distinct lease")
					var viewLease leases.Lease
					for _, candidate := range all {
						if candidate.ID != caller.l.ID {
							viewLease = candidate
						}
					}
					require.NotEmpty(t, viewLease.ID)
					require.NotEmpty(t, viewLease.Labels["containerd.io/gc.flat"])
					require.NotEmpty(t, viewLease.Labels["buildkit/lease.temporary"])
					if tc.bounded {
						expires, err := time.Parse(time.RFC3339, viewLease.Labels["containerd.io/gc.expire"])
						require.NoError(t, err)
						require.False(t, expires.Before(before.Add(tc.ttl).Truncate(time.Second)))
						require.False(t, expires.After(time.Now().Add(tc.ttl)))
					} else {
						require.NotContains(t, viewLease.Labels, "containerd.io/gc.expire")
					}
					resources, err := lm.ListResources(ctx, viewLease)
					require.NoError(t, err)
					require.Equal(t, []leases.Resource{{ID: key, Type: "snapshots/test"}}, resources,
						"view must be protected before Snapshotter.View")
					if tc.viewErr {
						return nil, injected
					}
					var mountErr error
					if tc.mountErr {
						mountErr = injected
					}
					return &immutableMountLeaseTestMountable{err: mountErr}, nil
				},
			}
			mountable, err := ref.Mount(ctx, true)
			switch {
			case tc.bounded && tc.ttl <= 0:
				require.ErrorContains(t, err, "mount lease expiration must be positive")
				require.Nil(t, mountable)
				require.False(t, calledView)
			case tc.viewErr:
				require.ErrorIs(t, err, injected)
				require.Nil(t, mountable)
			default:
				require.NoError(t, err)
				mounts, release, err := mountable.Mount()
				if tc.mountErr {
					require.ErrorIs(t, err, injected)
					require.Nil(t, release)
				} else {
					require.NoError(t, err)
					require.Len(t, mounts, 1)
					require.Contains(t, mounts[0].Options, "ro")
					require.NotNil(t, release)
					require.NoError(t, release())
				}
			}
			remaining, err := lm.List(context.Background())
			require.NoError(t, err)
			require.Equal(t, []leases.Lease{caller.l}, remaining, "cleanup must preserve the caller lease")
		})
	}
}

type immutableMountLeaseTestSnapshotter struct {
	MergeSnapshotter
	view func(context.Context, string, string) (MountableRef, error)
}

func (s *immutableMountLeaseTestSnapshotter) View(ctx context.Context, key, parent string, _ ...ctdsnapshots.Opt) (MountableRef, error) {
	return s.view(ctx, key, parent)
}

type immutableMountLeaseTestMountable struct {
	err error
}

func (m *immutableMountLeaseTestMountable) Mount() ([]mount.Mount, func() error, error) {
	if m.err != nil {
		return nil, nil, m.err
	}
	return []mount.Mount{{Type: "bind", Source: "/unused", Options: []string{"rw"}}}, nil, nil
}
