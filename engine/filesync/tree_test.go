package filesync

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/metadata"
	ctdsnapshots "github.com/containerd/containerd/v2/core/snapshots"
	"github.com/containerd/containerd/v2/pkg/namespaces"
	"github.com/containerd/containerd/v2/plugins/content/local"
	"github.com/containerd/containerd/v2/plugins/snapshots/native"
	"github.com/containerd/errdefs"
	"github.com/dagger/dagger/engine/filetree"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	bkcontainerd "github.com/dagger/dagger/engine/snapshots/containerd"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/util/fsxutil"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
)

type treeTestContent struct {
	content.Store
	files atomic.Int64
}

func (s *treeTestContent) Writer(ctx context.Context, opts ...content.WriterOpt) (content.Writer, error) {
	var parsed content.WriterOpts
	for _, opt := range opts {
		if err := opt(&parsed); err != nil {
			return nil, err
		}
	}
	if parsed.Desc.Digest == "" {
		s.files.Add(1) // PutTree supplies its known digest; PutFile streams bytes.
	}
	return s.Store.Writer(ctx, opts...)
}

type treeSyncFixture struct {
	ctx    context.Context
	db     *metadata.DB
	cm     bkcache.SnapshotManager
	blobs  *treeTestContent
	mirror *MirrorSharedState
	legacy *MirrorSharedState
}

func newTreeSyncFixture(t *testing.T) *treeSyncFixture {
	t.Helper()
	root := t.TempDir()
	sn, err := native.NewSnapshotter(filepath.Join(root, "snapshots"))
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, sn.Close()) })
	cs, err := local.NewStore(filepath.Join(root, "content"))
	require.NoError(t, err)
	disk, err := bolt.Open(filepath.Join(root, "metadata.db"), 0o600, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, disk.Close()) })
	const namespace = "filesync-tree-test"
	ctx := namespaces.WithNamespace(t.Context(), namespace)
	f := &treeSyncFixture{mirror: NewMirrorSharedState(t.TempDir()), legacy: NewMirrorSharedState(t.TempDir())}
	f.db = metadata.NewDB(disk, cs, map[string]ctdsnapshots.Snapshotter{"native": sn})
	require.NoError(t, f.db.Init(ctx))
	lm := bkcache.NewLeaseManager(metadata.NewLeaseManager(f.db), namespace)
	lease, err := lm.Create(ctx, leases.WithID("operation"))
	require.NoError(t, err)
	f.ctx = leases.WithLease(ctx, lease.ID)
	f.blobs = &treeTestContent{Store: bkcontainerd.NewContentStore(f.db.ContentStore(), namespace)}
	f.cm, err = bkcache.NewSnapshotManager(bkcache.SnapshotManagerOpt{
		Snapshotter:  bkcontainerd.NewSnapshotter("native", f.db.Snapshotter("native"), namespace),
		ContentStore: f.blobs, LeaseManager: lm, MountPoolRoot: filepath.Join(root, "mounts"),
	})
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, f.cm.Close())
		require.NoError(t, lm.Delete(context.WithoutCancel(ctx), lease))
	})
	return f
}

func (f *treeSyncFixture) local(t *testing.T, subdir, copyPath string, includes, excludes []string) *localFS {
	t.Helper()
	require.NoError(t, os.MkdirAll(filepath.Join(f.mirror.rootPath, subdir), 0o755))
	l, err := newLocalFS(f.mirror, subdir, includes, excludes, nil, copyPath)
	require.NoError(t, err)
	return l
}

func treeRemote(t *testing.T, source string, includes, excludes []string, gitignore bool) readFS {
	t.Helper()
	base, err := fsutil.NewFS(source)
	require.NoError(t, err)
	filtered, err := fsutil.NewFilterFS(base, &fsutil.FilterOpt{IncludePatterns: includes, ExcludePatterns: excludes})
	require.NoError(t, err)
	if gitignore {
		filtered, err = fsxutil.NewGitIgnoreMarkedFS(filtered, fsxutil.NewGitIgnoreMatcher(base))
		require.NoError(t, err)
	}
	return readFS{filtered}
}

func (f *treeSyncFixture) syncParity(t *testing.T, l *localFS, source string, gitignore bool) (*filetree.View, digest.Digest) {
	t.Helper()
	root, dgst, err := l.SyncTree(f.ctx, treeRemote(t, source, l.includes, l.excludes, gitignore), f.cm)
	require.NoError(t, err)
	// Keep legacy and CAS mirrors independent so both see the same transitions,
	// rather than comparing a cold import with an already-warmed mirror.
	require.NoError(t, os.MkdirAll(filepath.Join(f.legacy.rootPath, l.subdir), 0o755))
	legacyLocal, err := newLocalFS(f.legacy, l.subdir, l.includes, l.excludes, nil, l.copyPath)
	require.NoError(t, err)
	legacy, legacyDigest, err := legacyLocal.Sync(f.ctx, treeRemote(t, source, l.includes, l.excludes, gitignore), f.cm, false)
	require.NoError(t, err)
	require.NoError(t, legacy.Release(f.ctx))
	require.Equal(t, legacyDigest, dgst, "storage format must not change Dagger semantic identity")
	view, err := filetree.NewView(f.ctx, filetree.NewStore(f.blobs), *root)
	require.NoError(t, err)
	return view, dgst
}

func assertTreeFiles(t *testing.T, ctx context.Context, view *filetree.View, expected map[string]string, directories ...string) {
	t.Helper()
	actual := make(map[string]string)
	var dirs []string
	require.NoError(t, view.Walk(ctx, "/", func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		stat, err := view.Stat(name)
		require.NoError(t, err)
		require.Empty(t, stat.Xattrs, "mirror hints must not enter published metadata")
		if entry.IsDir() {
			dirs = append(dirs, name)
			return nil
		}
		r, err := view.Open(name)
		if err != nil {
			return err
		}
		data, err := io.ReadAll(r)
		actual[name] = string(data)
		return errors.Join(err, r.Close())
	}))
	require.Equal(t, expected, actual)
	require.ElementsMatch(t, directories, dirs)
}

func TestSyncTreeFiltersAndReincludedAncestors(t *testing.T) {
	for _, gitignore := range []bool{false, true} {
		t.Run(map[bool]string{false: "patterns", true: "gitignore"}[gitignore], func(t *testing.T) {
			f := newTreeSyncFixture(t)
			source := writeTree(t, map[string]string{"foo/keep": "yes", "foo/drop": "no", "outside": "no"})
			includes, excludes := []string{"foo"}, []string{"foo/drop"}
			expected := map[string]string{"foo/keep": "yes"}
			if gitignore {
				includes, excludes = nil, nil
				patterns := "foo/\n!foo/keep\noutside\n"
				require.NoError(t, os.WriteFile(filepath.Join(source, ".gitignore"), []byte(patterns), 0o644))
				expected[".gitignore"] = patterns
			}
			require.NoError(t, os.MkdirAll(filepath.Join(f.mirror.rootPath, "foo"), 0o755))
			require.NoError(t, os.WriteFile(filepath.Join(f.mirror.rootPath, "foo/drop"), []byte("old ignored bytes"), 0o644))
			l := f.local(t, "", "", includes, excludes)
			for range 2 { // cold then warm: ignored ancestors are not selected entries.
				view, _ := f.syncParity(t, l, source, gitignore)
				assertTreeFiles(t, f.ctx, view, expected, "foo")
			}
		})
	}
}

func TestSyncTreeWarmAndMissingBlobHint(t *testing.T) {
	f := newTreeSyncFixture(t)
	source := writeTree(t, map[string]string{"file": "retained payload"})
	l := f.local(t, "", "", nil, nil)
	view, _ := f.syncParity(t, l, source, false)
	writes := f.blobs.files.Load()
	require.EqualValues(t, 1, writes)
	view, _ = f.syncParity(t, l, source, false)
	require.Equal(t, writes, f.blobs.files.Load(), "warm file hint must avoid payload ingestion")
	root, err := filetree.NewStore(f.blobs).ReadTree(f.ctx, view.Root())
	require.NoError(t, err)
	file := *root.Entries[0].Object
	// Simulate collected/missing content while the private mirror hint survives.
	require.NoError(t, f.db.ContentStore().Delete(f.ctx, file.Digest))
	_, err = f.blobs.Info(f.ctx, file.Digest)
	require.True(t, errdefs.IsNotFound(err), "%v", err)
	view, _ = f.syncParity(t, l, source, false)
	require.Equal(t, writes+1, f.blobs.files.Load())
	assertTreeFiles(t, f.ctx, view, map[string]string{"file": "retained payload"})
}

func TestSyncTreeOverlappingImportCachedPaths(t *testing.T) {
	f := newTreeSyncFixture(t)
	outer := f.local(t, "", "", nil, nil)
	inner := f.local(t, "nested", "", nil, nil)
	filename := filepath.Join(f.mirror.rootPath, "nested/file")
	require.NoError(t, os.WriteFile(filename, []byte("shared"), 0o644))
	stat, err := fsutil.Stat(filename)
	require.NoError(t, err)
	stat.Path = "nested/file"
	outerChange, err := outer.GetPreviousChange(f.ctx, stat.Path, stat)
	require.NoError(t, err)
	defer outerChange.release()
	innerStat, err := fsutil.Stat(filename)
	require.NoError(t, err)
	innerChange, err := inner.GetPreviousChange(f.ctx, "file", innerStat)
	require.NoError(t, err)
	defer innerChange.release()
	require.Same(t, outerChange, innerChange)
	require.Equal(t, "nested/file", innerChange.result().stat.Path)
	in, err := f.cm.(bkcache.FileTreeManager).FileTreeIngest(f.ctx)
	require.NoError(t, err)
	root, err := inner.ingestTree(f.ctx, in, []CachedChange{innerChange}, map[string]struct{}{"file": {}})
	require.NoError(t, err)
	view, err := filetree.NewView(f.ctx, filetree.NewStore(f.blobs), root)
	require.NoError(t, err)
	assertTreeFiles(t, f.ctx, view, map[string]string{"file": "shared"})
}

func TestSyncTreeHardlinksWithOutsideRepresentative(t *testing.T) {
	f := newTreeSyncFixture(t)
	source := writeTree(t, map[string]string{"a-target": "linked", "keep-other/unrelated": "not selected"})
	require.NoError(t, os.Mkdir(filepath.Join(source, "keep"), 0o755))
	for _, name := range []string{"b", "c"} {
		require.NoError(t, os.Link(filepath.Join(source, "a-target"), filepath.Join(source, "keep", name)))
	}
	l := f.local(t, "project", "keep", nil, nil)
	view, _ := f.syncParity(t, l, source, false)
	assertTreeFiles(t, f.ctx, view, map[string]string{"b": "linked", "c": "linked"})
	b, err := view.Stat("b")
	require.NoError(t, err)
	c, err := view.Stat("c")
	require.NoError(t, err)
	require.Empty(t, b.Linkname, "first selected alias becomes the representative")
	require.Equal(t, "b", c.Linkname, "internal aliases must not point outside the selected root")
}
