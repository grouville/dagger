package filesync

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/errdefs"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/snapshots/config"
	"github.com/dagger/dagger/engine/snapshots/testutil"
	"github.com/dagger/dagger/internal/buildkit/util/compression"
	"github.com/dagger/dagger/internal/fsutil"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestSyncSnapshotSeedsTransferAndRestart(t *testing.T) {
	ctx := context.Background()
	files := map[string]string{"src/lib.rs": "original"}
	for i := range 64 {
		files[fmt.Sprintf("unchanged/%03d", i)] = strings.Repeat(fmt.Sprintf("file %03d\n", i), 1024)
	}
	clientRoot := writeTree(t, files)
	// OCI layer timestamps have second precision.
	for name := range files {
		assert.NilError(t, os.Chtimes(filepath.Join(clientRoot, name), testutil.FileTime, testutil.FileTime))
	}
	client, err := fsutil.NewFS(clientRoot)
	assert.NilError(t, err)
	producer, consumer := testutil.NewStore(t), testutil.NewStore(t)
	mirror := t.TempDir()
	seeds := &SnapshotSeeds{}
	var previous bkcache.ImmutableRef
	var previousOwner string
	var latestID string
	var producerIDs []string
	var initialBytes int64
	for i := range 3 {
		local, err := newLocalFS(NewMirrorSharedState(mirror), "", nil, nil, nil, "")
		assert.NilError(t, err)
		local.seeds, local.seedScope = seeds, "workspace"
		if i != 0 {
			assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, "src/lib.rs"), []byte(fmt.Sprintf("edit %d", i)), 0o640))
			assert.NilError(t, os.Chmod(filepath.Join(clientRoot, "src/lib.rs"), 0o640))
			modified := testutil.FileTime.Add(time.Duration(i) * time.Second)
			assert.NilError(t, os.Chtimes(filepath.Join(clientRoot, "src/lib.rs"), modified, modified))
		}
		ref, owner := syncPublished(t, producer, local, client)
		latestID = ref.SnapshotID()
		producerIDs = append(producerIDs, latestID)
		if previous != nil {
			assert.NilError(t, previous.Release(ctx))
			assert.NilError(t, producer.Manager.RemoveLease(ctx, previousOwner))
		}
		previous, previousOwner = ref, owner
		producer.GC(t)
		depth := 0
		if i == 1 {
			depth = 1
		}
		assert.Equal(t, seedParentDepth(t, producer.Manager, latestID), depth)
		chain, err := ref.ExportChain(ctx, config.RefConfig{Compression: compression.New(compression.Uncompressed)})
		assert.NilError(t, err)
		assert.Equal(t, len(chain.Layers), depth+1)
		provider := &testutil.Provider{InfoReaderProvider: chain.Provider}
		imported, err := consumer.Manager.ImportChain(ctx, &bkcache.ExportChain{Layers: chain.Layers, Provider: provider})
		assert.NilError(t, err)
		assert.Equal(t, provider.Reads.Load(), int64(1), "a warm consumer reads only the new layer")
		assert.Assert(t, is.DeepEqual(seedTestTree(t, testutil.Root(t, ref)), seedTestTree(t, testutil.Root(t, imported))))
		var bytes int64
		for _, layer := range chain.Layers {
			bytes += layer.Descriptor.Size
		}
		if i == 0 {
			initialBytes = bytes
		} else if i == 1 {
			delta := chain.Layers[1].Descriptor.Size
			assert.Assert(t, delta < initialBytes/4, "the changed-file layer must not contain the unchanged fixture")
			t.Logf("initial transfer=%d bytes; edited cold transfer=%d bytes; edited warm transfer=%d bytes", initialBytes, bytes, delta)
			cold := testutil.NewStore(t)
			coldProvider := &testutil.Provider{InfoReaderProvider: chain.Provider}
			coldRef, err := cold.Manager.ImportChain(ctx, &bkcache.ExportChain{Layers: chain.Layers, Provider: coldProvider})
			assert.NilError(t, err)
			assert.Equal(t, coldProvider.Reads.Load(), int64(len(chain.Layers)))
			assert.Assert(t, is.DeepEqual(seedTestTree(t, testutil.Root(t, ref)), seedTestTree(t, testutil.Root(t, coldRef))))
			assert.NilError(t, coldRef.Release(ctx))
			assert.NilError(t, bkcache.ReleaseTransferLeasesAfterRestart(ctx, cold.Leases))
		}
		assert.NilError(t, consumer.Manager.AttachLease(ctx, "latest-import", imported.SnapshotID()))
		importedID := imported.SnapshotID()
		assert.NilError(t, imported.Release(ctx))
		assert.NilError(t, chain.Release(ctx))
		if i == 1 {
			// Reopen both managers and discard the process-local hint. The
			// durable snapshots survive; the next edit takes the full-copy path.
			assert.NilError(t, previous.Release(ctx))
			previous = nil
			producer.Reload(t)
			consumer.Reload(t)
			seeds = &SnapshotSeeds{}
			assert.NilError(t, bkcache.ReleaseTransferLeasesAfterRestart(ctx, consumer.Leases))
			producer.GC(t)
			consumer.GC(t)
			reopened, err := producer.Manager.GetBySnapshotID(ctx, latestID)
			assert.NilError(t, err)
			assertSyncedFile(t, reopened, "src/lib.rs", "edit 1")
			assert.NilError(t, reopened.Release(ctx))
			reopened, err = consumer.Manager.GetBySnapshotID(ctx, importedID)
			assert.NilError(t, err)
			assertSyncedFile(t, reopened, "src/lib.rs", "edit 1")
			assert.NilError(t, reopened.Release(ctx))
			assert.NilError(t, producer.Manager.RemoveLease(ctx, previousOwner))
		}
	}
	assert.NilError(t, previous.Release(ctx))
	assert.NilError(t, producer.Manager.RemoveLease(ctx, previousOwner))
	producer.GC(t)
	for _, id := range producerIDs {
		_, err := producer.Snapshots.Stat(ctx, id)
		assert.Assert(t, errdefs.IsNotFound(err), "snapshot %s must be collectable despite its hint: %v", id, err)
	}
	assert.NilError(t, consumer.Leases.Delete(ctx, leases.Lease{ID: "latest-import"}))
	assert.NilError(t, bkcache.ReleaseTransferLeasesAfterRestart(ctx, consumer.Leases))
	consumer.GC(t)
}
