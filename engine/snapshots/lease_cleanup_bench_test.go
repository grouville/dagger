package snapshots

import (
	"context"
	"fmt"
	"testing"

	ctdsnapshots "github.com/containerd/containerd/v2/core/snapshots"
	"github.com/stretchr/testify/require"
)

// Removing a small owner should not scale with snapshots held by other owners.
func BenchmarkRemoveLease(b *testing.B) {
	for _, count := range []int{128, 1024, 8192} {
		b.Run(fmt.Sprintf("unrelated=%d", count), func(b *testing.B) {
			ctx := context.Background()
			cm := newApplySnapshotDiffTestManager(b)
			sn := cm.Snapshotter.(*applySnapshotDiffTestSnapshotter)
			for i := range count {
				id := fmt.Sprintf("unrelated-%d", i)
				sn.snapshots[id] = ctdsnapshots.Info{Name: id}
				require.NoError(b, cm.AttachLease(ctx, "kept", id))
			}
			sn.snapshots["removed"] = ctdsnapshots.Info{Name: "removed"}
			b.ReportAllocs()
			for b.Loop() {
				require.NoError(b, cm.AttachLease(ctx, "removed", "removed"))
				require.NoError(b, cm.RemoveLease(ctx, "removed"))
			}
		})
	}
}
