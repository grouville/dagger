//go:build linux

package core

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/containerd/containerd/v2/plugins/snapshots/native"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	bkcontainerd "github.com/dagger/dagger/engine/snapshots/containerd"
	"github.com/stretchr/testify/require"
)

func TestClientFilesyncMirrorRefreshesMutableUsage(t *testing.T) {
	ctx := context.Background()
	snapshotter, err := native.NewSnapshotter(t.TempDir())
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, snapshotter.Close()) })
	manager, err := bkcache.NewSnapshotManager(bkcache.SnapshotManagerOpt{
		Snapshotter:   bkcontainerd.NewSnapshotter("native", snapshotter, "mirror-usage-test"),
		MountPoolRoot: t.TempDir(),
	})
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, manager.Close()) })
	ref, err := manager.New(ctx, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, ref.Release(ctx)) })
	mountable, err := ref.Mount(ctx, false)
	require.NoError(t, err)
	mounter := bkcache.LocalMounter(mountable)
	root, err := mounter.Mount()
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, mounter.Unmount()) })

	mirror := &ClientFilesyncMirror{snapshot: ref}
	usage := func() int64 {
		size, known, err := mirror.CacheUsageSize(ctx, nil, ref.SnapshotID())
		require.NoError(t, err)
		require.True(t, known)
		return size
	}
	empty := usage()
	path := filepath.Join(root, "blob")
	require.NoError(t, os.WriteFile(path, bytes.Repeat([]byte("x"), 1<<20), 0o600))
	grown := usage()
	require.GreaterOrEqual(t, grown-empty, int64(1<<20), "a prior size query must not hide new cache files")
	require.NoError(t, os.Remove(path))
	require.Less(t, usage(), grown, "removing the cache link must refresh usage too")
}
