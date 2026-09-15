//go:build linux && privileged

package filesync

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	bkcontenthash "github.com/dagger/dagger/engine/contenthash"
	"github.com/dagger/dagger/engine/filetree"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/stretchr/testify/require"
)

func TestSyncTreeReusesSemanticRootAndRepairsMissingLeaf(t *testing.T) {
	f := newTreeSyncFixture(t)
	source := writeTree(t, map[string]string{"a": "same bytes"})
	require.NoError(t, os.Link(filepath.Join(source, "a"), filepath.Join(source, "z")))
	l := f.local(t, "", "", nil, nil)
	root, dgst, err := l.SyncTree(f.ctx, treeRemote(t, source, nil, nil, false), f.cm)
	require.NoError(t, err)
	manager := f.cm.(bkcache.FileTreeManager)
	ref, err := manager.MaterializeFileTree(f.ctx, *root, "")
	require.NoError(t, err)
	defer ref.Release(f.ctx)
	require.NoError(t, (bkcontenthash.CacheRefMetadata{RefMetadata: ref.(bkcache.RefMetadata)}).SetContentHashKey(dgst))

	// Same bytes but different hardlink topology are semantically equivalent
	// under existing filesync rules. Select the earlier root, not just its view.
	require.NoError(t, os.Remove(filepath.Join(source, "z")))
	require.NoError(t, os.WriteFile(filepath.Join(source, "z"), []byte("same bytes"), 0o644))
	selected, sameDigest, err := l.SyncTree(f.ctx, treeRemote(t, source, nil, nil, false), f.cm)
	require.NoError(t, err)
	require.Equal(t, dgst, sameDigest)
	require.Equal(t, root, selected)
	store := filetree.NewStore(f.blobs)
	view, err := filetree.NewView(f.ctx, store, *selected)
	require.NoError(t, err)
	alias, err := view.Stat("z")
	require.NoError(t, err)
	require.Equal(t, "a", alias.Linkname)

	// An intact filesystem view must not hide a missing CAS descendant. The
	// optional hit becomes a miss, and the held mirror repairs the leaf object.
	tree, err := store.ReadTree(f.ctx, *root)
	require.NoError(t, err)
	blob := *tree.Entries[0].Object
	require.NoError(t, f.db.ContentStore().Delete(f.ctx, blob.Digest))
	writes := f.blobs.files.Load()
	repaired, repairedDigest, err := l.SyncTree(f.ctx, treeRemote(t, source, nil, nil, false), f.cm)
	require.NoError(t, err)
	require.Equal(t, dgst, repairedDigest)
	require.Greater(t, f.blobs.files.Load(), writes)
	view, err = filetree.NewView(f.ctx, store, *repaired)
	require.NoError(t, err)
	assertTreeFiles(t, f.ctx, view, map[string]string{"a": "same bytes", "z": "same bytes"})
}

// An empty legacy import must mount its snapshot to compute the checksum; this
// parity test therefore needs the same mount privileges as the engine.
func TestSyncTreeEmptyEditDeleteRevert(t *testing.T) {
	f := newTreeSyncFixture(t)
	source := t.TempDir()
	l := f.local(t, "", "", nil, nil)
	view, _ := f.syncParity(t, l, source, false)
	assertTreeFiles(t, f.ctx, view, map[string]string{})
	require.NoError(t, os.Mkdir(filepath.Join(source, "empty"), 0o755))
	write := func(name, value string, tick int64) {
		t.Helper()
		filename := filepath.Join(source, name)
		require.NoError(t, os.WriteFile(filename, []byte(value), 0o644))
		require.NoError(t, os.Chtimes(filename, time.Unix(1000+tick, 0), time.Unix(1000+tick, 0)))
	}
	write("file", "before", 1)
	write("gone", "restored", 1)
	view, original := f.syncParity(t, l, source, false)
	assertTreeFiles(t, f.ctx, view, map[string]string{"file": "before", "gone": "restored"}, "empty")
	write("file", "after!", 2)
	require.NoError(t, os.Remove(filepath.Join(source, "gone")))
	view, changed := f.syncParity(t, l, source, false)
	require.NotEqual(t, original, changed, "same-size edits must still invalidate")
	assertTreeFiles(t, f.ctx, view, map[string]string{"file": "after!"}, "empty")
	write("file", "before", 1)
	write("gone", "restored", 1)
	view, reverted := f.syncParity(t, l, source, false)
	require.Equal(t, original, reverted)
	assertTreeFiles(t, f.ctx, view, map[string]string{"file": "before", "gone": "restored"}, "empty")
}
