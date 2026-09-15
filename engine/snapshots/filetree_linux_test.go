//go:build linux && privileged

package snapshots_test

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/metadata"
	ctdsnapshots "github.com/containerd/containerd/v2/core/snapshots"
	"github.com/containerd/containerd/v2/pkg/namespaces"
	"github.com/containerd/containerd/v2/plugins/content/local"
	"github.com/containerd/containerd/v2/plugins/snapshots/native"
	"github.com/containerd/containerd/v2/plugins/snapshots/overlay"
	"github.com/containerd/containerd/v2/plugins/snapshots/overlay/overlayutils"
	"github.com/containerd/errdefs"
	"github.com/dagger/dagger/engine/filetree"
	"github.com/dagger/dagger/engine/snapshots"
	snapshotcontainerd "github.com/dagger/dagger/engine/snapshots/containerd"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
	"golang.org/x/sync/errgroup"
)

type fileTreeSnapshotFixture struct {
	ctx  context.Context
	db   *metadata.DB
	sn   ctdsnapshots.Snapshotter
	lm   leases.Manager
	cm   snapshots.SnapshotManager
	opts snapshots.SnapshotManagerOpt
}

func newFileTreeSnapshotFixture(t *testing.T, name string) *fileTreeSnapshotFixture {
	t.Helper()
	root := t.TempDir()
	snapshotRoot := filepath.Join(root, "snapshots")
	var raw ctdsnapshots.Snapshotter
	var err error
	if name == "overlayfs" {
		// These tests run in privileged engine-dev. Unsupported overlay is a
		// failed prerequisite, never silently reported as passing coverage.
		require.NoError(t, overlayutils.Supported(snapshotRoot))
		raw, err = overlay.NewSnapshotter(snapshotRoot)
	} else {
		raw, err = native.NewSnapshotter(snapshotRoot)
	}
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, raw.Close()) })
	content, err := local.NewStore(filepath.Join(root, "content"))
	require.NoError(t, err)
	disk, err := bolt.Open(filepath.Join(root, "metadata.db"), 0o600, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, disk.Close()) })
	const namespace = "filetree-snapshots-test"
	f := &fileTreeSnapshotFixture{ctx: namespaces.WithNamespace(t.Context(), namespace)}
	f.db = metadata.NewDB(disk, content, map[string]ctdsnapshots.Snapshotter{name: raw})
	require.NoError(t, f.db.Init(f.ctx))
	f.sn = f.db.Snapshotter(name)
	f.lm = snapshots.NewLeaseManager(metadata.NewLeaseManager(f.db), namespace)
	f.opts = snapshots.SnapshotManagerOpt{
		Snapshotter:  snapshotcontainerd.NewSnapshotter(name, f.sn, namespace),
		ContentStore: snapshotcontainerd.NewContentStore(f.db.ContentStore(), namespace),
		LeaseManager: f.lm, MountPoolRoot: filepath.Join(root, "mounts"),
	}
	f.cm, err = snapshots.NewSnapshotManager(f.opts)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, f.cm.Close()) })
	return f
}

func (f *fileTreeSnapshotFixture) operation(t *testing.T, id string) (context.Context, func()) {
	t.Helper()
	lease, err := f.lm.Create(f.ctx, leases.WithID(id))
	require.NoError(t, err)
	release := func() {
		err := f.lm.Delete(context.WithoutCancel(f.ctx), lease)
		if !errdefs.IsNotFound(err) {
			require.NoError(t, err)
		}
	}
	t.Cleanup(release)
	return leases.WithLease(f.ctx, id), release
}

func (f *fileTreeSnapshotFixture) gc(t *testing.T) {
	t.Helper()
	_, err := f.db.GarbageCollect(f.ctx)
	require.NoError(t, err)
}

func fileTreeMetadata() filetree.Metadata {
	return filetree.Metadata{Mode: 0o755, UID: uint32(os.Getuid()), GID: uint32(os.Getgid()), ModTime: 1700000000000001234}
}

func fileTreeFile(t *testing.T, in *filetree.Ingest, name, value string) filetree.Entry {
	t.Helper()
	obj, err := in.PutFile(strings.NewReader(value), int64(len(value)))
	require.NoError(t, err)
	md := fileTreeMetadata()
	md.Mode = 0o644
	return filetree.Entry{Name: []byte(name), Kind: filetree.File, Metadata: &md, Object: &obj}
}

func fileTreeRoot(t *testing.T, in *filetree.Ingest, entries ...filetree.Entry) filetree.Object {
	t.Helper()
	root, err := in.PutTree(filetree.Tree{Version: filetree.TreeVersion, Metadata: fileTreeMetadata(), Entries: entries})
	require.NoError(t, err)
	return root
}

func (f *fileTreeSnapshotFixture) materialize(t *testing.T, ctx context.Context, root filetree.Object, parent string) snapshots.ImmutableRef {
	t.Helper()
	ref, err := f.cm.(snapshots.FileTreeManager).MaterializeFileTree(ctx, root, parent)
	require.NoError(t, err)
	return ref
}

func (f *fileTreeSnapshotFixture) assertTree(t *testing.T, ref snapshots.ImmutableRef, root filetree.Object) {
	t.Helper()
	view, err := filetree.NewView(f.ctx, filetree.NewStore(f.opts.ContentStore), root)
	require.NoError(t, err)
	mountable, err := ref.Mount(f.ctx, true)
	require.NoError(t, err)
	mounter := snapshots.LocalMounter(mountable)
	directory, err := mounter.Mount()
	require.NoError(t, err)
	defer func() { require.NoError(t, mounter.Unmount()) }()
	var actual []string
	require.NoError(t, filepath.WalkDir(directory, func(name string, _ fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(directory, name)
		actual = append(actual, rel)
		return err
	}))
	require.ElementsMatch(t, append(view.Entries(), "."), actual)
	for _, name := range actual {
		filename := filepath.Join(directory, name)
		info, err := os.Lstat(filename)
		require.NoError(t, err)
		want, err := view.Stat(name)
		require.NoError(t, err)
		require.Equal(t, want.Mode(), info.Mode(), name)
		require.Equal(t, want.ModTime().UnixNano(), info.ModTime().UnixNano(), name)
		if info.Mode().IsRegular() {
			r, err := view.Open(name)
			require.NoError(t, err)
			expected, err := io.ReadAll(r)
			require.NoError(t, errors.Join(err, r.Close()))
			data, err := os.ReadFile(filename)
			require.NoError(t, err)
			require.Equal(t, expected, data, name)
			if want.Linkname != "" {
				target, err := os.Stat(filepath.Join(directory, want.Linkname))
				require.NoError(t, err)
				require.True(t, os.SameFile(info, target), "hardlink %s -> %s", name, want.Linkname)
			}
		} else if info.Mode()&os.ModeSymlink != 0 {
			target, err := os.Readlink(filename)
			require.NoError(t, err)
			require.Equal(t, want.Linkname, target)
		}
	}
}

func TestFileTreeSnapshotDelta(t *testing.T) {
	for _, name := range []string{"native", "overlayfs"} {
		t.Run(name, func(t *testing.T) {
			f := newFileTreeSnapshotFixture(t, name)
			ctx, _ := f.operation(t, "delta")
			in, err := f.cm.(snapshots.FileTreeManager).FileTreeIngest(ctx)
			require.NoError(t, err)
			child := fileTreeRoot(t, in, fileTreeFile(t, in, "child", "nested"))
			unchanged := fileTreeFile(t, in, "unchanged", "keep")
			alias := filetree.Entry{Name: []byte("alias"), Kind: filetree.Hardlink, Linkname: []byte("target")}
			newAlias := filetree.Entry{Name: []byte("new-alias"), Kind: filetree.Hardlink, Linkname: []byte("target")}
			entries := []filetree.Entry{
				fileTreeFile(t, in, "target", "old"), unchanged, alias, fileTreeFile(t, in, "gone", "delete"),
				{Name: []byte("swap"), Kind: filetree.Directory, Object: &child},
			}
			before := fileTreeRoot(t, in, entries...)
			first := f.materialize(t, ctx, before, "")
			defer first.Release(f.ctx)
			f.assertTree(t, first, before)
			// Adding an alias must not leave the old alias on an overlay lower inode.
			entries = append(entries, newAlias)
			linked := fileTreeRoot(t, in, entries...)
			second := f.materialize(t, ctx, linked, first.SnapshotID())
			defer second.Release(f.ctx)
			f.assertTree(t, second, linked)
			linkMD := fileTreeMetadata()
			linkMD.Mode = 0o777
			after := fileTreeRoot(t, in, fileTreeFile(t, in, "target", "new"), unchanged, alias, newAlias,
				fileTreeFile(t, in, "swap", "replaced directory"),
				filetree.Entry{Name: []byte("added"), Kind: filetree.Directory, Object: &child},
				filetree.Entry{Name: []byte("symlink"), Kind: filetree.Symlink, Metadata: &linkMD, Linkname: []byte("../outside")})
			third := f.materialize(t, ctx, after, second.SnapshotID())
			defer third.Release(f.ctx)
			f.assertTree(t, third, after)
			f.assertTree(t, first, before)
			f.assertTree(t, second, linked)
		})
	}
}

func TestFileTreeSnapshotOwnershipAndReconstruction(t *testing.T) {
	for _, name := range []string{"native", "overlayfs"} {
		t.Run(name, func(t *testing.T) {
			f := newFileTreeSnapshotFixture(t, name)
			oldCtx, releaseOld := f.operation(t, "old-operation")
			in, err := f.cm.(snapshots.FileTreeManager).FileTreeIngest(oldCtx)
			require.NoError(t, err)
			root := fileTreeRoot(t, in, fileTreeFile(t, in, "file", "retained CAS bytes"))
			first := f.materialize(t, oldCtx, root, "")
			id := first.SnapshotID()
			require.NoError(t, f.cm.AttachLease(f.ctx, "dagql/result/old/snapshot", id))
			require.NoError(t, f.cm.(snapshots.ContentManager).AttachContentLease(f.ctx, "dagql/result/cas/content/root", root.Digest))
			newCtx, releaseNew := f.operation(t, "new-operation")
			reused := f.materialize(t, newCtx, root, "")
			require.Equal(t, id, reused.SnapshotID(), "exact root must reuse its immutable view")
			require.NoError(t, first.Release(f.ctx))
			require.NoError(t, f.cm.RemoveLease(f.ctx, "dagql/result/old/snapshot"))
			releaseOld()
			f.gc(t)
			f.assertTree(t, reused, root)
			require.NoError(t, reused.Release(f.ctx))
			releaseNew()
			f.gc(t)
			_, err = f.sn.Stat(f.ctx, id)
			require.True(t, errdefs.IsNotFound(err), "derived snapshot must be collectible: %v", err)
			var remaining []string
			require.NoError(t, f.sn.Walk(f.ctx, func(_ context.Context, info ctdsnapshots.Info) error {
				remaining = append(remaining, info.Name)
				return nil
			}))
			require.Empty(t, remaining, "content ownership must not retain derived snapshots")
			ctx, _ := f.operation(t, "reconstruction")
			reconstructed := f.materialize(t, ctx, root, id)
			defer reconstructed.Release(f.ctx)
			require.NotEqual(t, id, reconstructed.SnapshotID())
			f.assertTree(t, reconstructed, root)
		})
	}
}

func TestFileTreeSnapshotHintSurvivesManagerRestart(t *testing.T) {
	for _, name := range []string{"native", "overlayfs"} {
		t.Run(name, func(t *testing.T) {
			f := newFileTreeSnapshotFixture(t, name)
			ctx, _ := f.operation(t, "restart")
			in, err := f.cm.(snapshots.FileTreeManager).FileTreeIngest(ctx)
			require.NoError(t, err)
			before := fileTreeRoot(t, in, fileTreeFile(t, in, "file", "before restart"))
			first := f.materialize(t, ctx, before, "")
			id := first.SnapshotID()
			require.NoError(t, first.Release(f.ctx))
			require.NoError(t, f.cm.Close())
			f.cm, err = snapshots.NewSnapshotManager(f.opts)
			require.NoError(t, err)
			after := fileTreeRoot(t, in, fileTreeFile(t, in, "file", "after restart"))
			ref := f.materialize(t, ctx, after, id)
			defer ref.Release(f.ctx)
			info, err := f.sn.Stat(f.ctx, ref.SnapshotID())
			require.NoError(t, err)
			if name == "overlayfs" {
				require.Equal(t, id, info.Parent, "persisted root label must enable delta, not full reconstruction")
			} else {
				require.Empty(t, info.Parent, "native Prepare does not preserve directory mtimes; reconstruct from CAS")
			}
			f.assertTree(t, ref, after)
		})
	}
}

func TestFileTreeSnapshotConcurrentReuseAndSourceHint(t *testing.T) {
	f := newFileTreeSnapshotFixture(t, "overlayfs")
	ctx, _ := f.operation(t, "concurrent")
	manager := f.cm.(snapshots.FileTreeManager)
	in, err := manager.FileTreeIngest(ctx)
	require.NoError(t, err)
	before := fileTreeRoot(t, in, fileTreeFile(t, in, "file", "before"))
	refs := make([]snapshots.ImmutableRef, 8)
	var group errgroup.Group
	for i := range refs {
		group.Go(func() error {
			ref, err := manager.MaterializeFileTree(ctx, before, "", snapshots.WithFileTreeSourceKey("source"))
			refs[i] = ref
			return err
		})
	}
	require.NoError(t, group.Wait())
	id := refs[0].SnapshotID()
	for _, ref := range refs {
		require.Equal(t, id, ref.SnapshotID(), "concurrent identical roots must share one view")
		require.NoError(t, ref.Release(f.ctx))
	}
	after := fileTreeRoot(t, in, fileTreeFile(t, in, "file", "after"))
	ref, err := manager.MaterializeFileTree(ctx, after, "", snapshots.WithFileTreeSourceKey("source"))
	require.NoError(t, err)
	defer ref.Release(f.ctx)
	info, err := f.sn.Stat(f.ctx, ref.SnapshotID())
	require.NoError(t, err)
	require.Equal(t, id, info.Parent, "a source hint should enable delta reuse without becoming content identity")
	f.assertTree(t, ref, after)
}

func TestFileTreeSnapshotRootHintRetainsOnlyContent(t *testing.T) {
	f := newFileTreeSnapshotFixture(t, "native")
	oldCtx, releaseOld := f.operation(t, "old")
	manager := f.cm.(snapshots.FileTreeManager)
	in, err := manager.FileTreeIngest(oldCtx)
	require.NoError(t, err)
	root := fileTreeRoot(t, in, fileTreeFile(t, in, "a", "retained"),
		filetree.Entry{Name: []byte("z"), Kind: filetree.Hardlink, Linkname: []byte("a")})
	first := f.materialize(t, oldCtx, root, "")
	id := first.SnapshotID()
	ctx, _ := f.operation(t, "new")
	selected, err := manager.FileTreeRoot(ctx, id)
	require.NoError(t, err)
	require.Equal(t, root, selected)
	require.NoError(t, first.Release(f.ctx))
	releaseOld()
	f.gc(t)
	_, err = f.sn.Stat(f.ctx, id)
	require.True(t, errdefs.IsNotFound(err), "root selection must not retain the old view: %v", err)
	reconstructed := f.materialize(t, ctx, selected, id)
	defer reconstructed.Release(f.ctx)
	f.assertTree(t, reconstructed, root)
}

func TestFileTreeSnapshotRootHintValidation(t *testing.T) {
	for _, mode := range []string{"missing-view", "legacy-view", "missing-root", "missing-leaf", "invalid-label"} {
		t.Run(mode, func(t *testing.T) {
			f := newFileTreeSnapshotFixture(t, "native")
			ctx, _ := f.operation(t, "hint")
			manager := f.cm.(snapshots.FileTreeManager)
			in, err := manager.FileTreeIngest(ctx)
			require.NoError(t, err)
			file := fileTreeFile(t, in, "file", "bytes")
			root := fileTreeRoot(t, in, file)
			ref := f.materialize(t, ctx, root, "")
			defer ref.Release(f.ctx)
			id := ref.SnapshotID()
			switch mode {
			case "missing-view":
				id = "absent"
			case "legacy-view", "invalid-label":
				label := ""
				if mode == "invalid-label" {
					label = "not-json"
				}
				_, err := f.sn.Update(f.ctx, ctdsnapshots.Info{Name: id, Labels: map[string]string{"dagger.io/filetree.root.v1": label}}, "labels.dagger.io/filetree.root.v1")
				require.NoError(t, err)
			case "missing-root":
				require.NoError(t, f.db.ContentStore().Delete(f.ctx, root.Digest))
			case "missing-leaf":
				require.NoError(t, f.db.ContentStore().Delete(f.ctx, file.Object.Digest))
			}
			_, err = manager.FileTreeRoot(ctx, id)
			if mode == "invalid-label" {
				require.ErrorContains(t, err, "decode filetree root")
				require.False(t, errdefs.IsNotFound(err) || snapshots.IsNotFound(err))
			} else {
				require.True(t, errdefs.IsNotFound(err) || snapshots.IsNotFound(err), "%v", err)
			}
		})
	}
}
