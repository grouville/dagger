//go:build linux && privileged

package core

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/metadata"
	ctdsnapshots "github.com/containerd/containerd/v2/core/snapshots"
	"github.com/containerd/containerd/v2/pkg/namespaces"
	"github.com/containerd/containerd/v2/plugins/content/local"
	"github.com/containerd/containerd/v2/plugins/snapshots/native"
	"github.com/containerd/errdefs"
	"github.com/dagger/dagger/dagql"
	bkcontenthash "github.com/dagger/dagger/engine/contenthash"
	"github.com/dagger/dagger/engine/filetree"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	bkcontainerd "github.com/dagger/dagger/engine/snapshots/containerd"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/hashutil"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
	"golang.org/x/sys/unix"
)

// This exercises the real Directory codec and DagQL disk checkpoint, not a
// replayed Host.directory request. Source files and a filesync mirror never
// exist: after the ingest lease is removed, only the result owns the CAS root.
func TestDirectoryFileTreePersistenceRematerializesWithoutSource(t *testing.T) {
	f := newDirectoryFileTreePersistenceFixture(t)
	const contents = "pub fn retained() -> bool { true }\n"
	lease, err := f.opts.LeaseManager.Create(f.ctx, leases.WithID("test-ingest"))
	require.NoError(t, err)
	defer func() {
		err := f.opts.LeaseManager.Delete(context.WithoutCancel(f.ctx), lease)
		if !errdefs.IsNotFound(err) {
			require.NoError(t, err)
		}
	}()
	in, err := f.cm.(bkcache.FileTreeManager).FileTreeIngest(leases.WithLease(f.ctx, lease.ID))
	require.NoError(t, err)
	blob, err := in.PutFile(strings.NewReader(contents), int64(len(contents)))
	require.NoError(t, err)
	md := filetree.Metadata{Mode: 0o755, UID: uint32(os.Getuid()), GID: uint32(os.Getgid()), ModTime: 1700000000000001234}
	fileMD := md
	fileMD.Mode = 0o644
	// Seed a real CacheContext with engine-owned XXH3 path hashes. The separate
	// filesync parity regression compares these hashes to an actual legacy sync;
	// this source-free test checks their lifetime through GC and two restarts.
	scratch, err := f.cm.New(leases.WithLease(f.ctx, lease.ID), nil)
	require.NoError(t, err)
	checksums, err := bkcontenthash.GetCacheContext(f.ctx, scratch.(bkcache.RefMetadata))
	require.NoError(t, err)
	for _, stat := range []*types.Stat{
		{Path: "src", Mode: uint32(os.ModeDir) | 0o755},
		{Path: "src/lib.rs", Mode: 0o644},
		{Path: "alias.rs", Mode: 0o644, Linkname: "src/lib.rs"},
	} {
		info := persistedFileTreeChecksumInfo{StatInfo: &fsutil.StatInfo{Stat: stat}, hash: hashutil.HashStrings(stat.Path)}
		require.NoError(t, checksums.HandleChange(fsutil.ChangeKindAdd, stat.Path, info, nil))
	}
	f.checksums = make(map[string]digest.Digest)
	for _, name := range []string{"/", "/src", "/src/lib.rs", "/alias.rs"} {
		f.checksums[name], err = checksums.Checksum(f.ctx, scratch, name, bkcontenthash.ChecksumOpts{})
		require.NoError(t, err)
	}
	checksumData, err := bkcontenthash.MarshalCacheContext(checksums)
	require.NoError(t, err)
	checksumObject, err := in.PutFile(bytes.NewReader(checksumData), int64(len(checksumData)))
	require.NoError(t, err)
	require.NoError(t, scratch.Release(f.ctx))
	child, err := in.PutTree(filetree.Tree{Version: filetree.TreeVersion, Metadata: md, Entries: []filetree.Entry{
		{Name: []byte("lib.rs"), Kind: filetree.File, Metadata: &fileMD, Object: &blob},
	}})
	require.NoError(t, err)
	root, err := in.PutTree(filetree.Tree{Version: filetree.TreeVersion, Metadata: md, Checksums: &checksumObject, Entries: []filetree.Entry{
		{Name: []byte("src"), Kind: filetree.Directory, Object: &child},
		{Name: []byte("alias.rs"), Kind: filetree.Hardlink, Linkname: []byte("src/lib.rs")},
	}})
	require.NoError(t, err)

	ctx, srv := f.openCache(t)
	call := testResultCall("persist-filetree-directory", &Directory{}, nil)
	dir := NewFileTreeDirectory(Platform{OS: "linux", Architecture: "amd64"}, root, f.checksums["/"], "test-source-hint")
	initial, err := dagql.NewObjectResultForCall(dir, srv, call)
	require.NoError(t, err)
	res, err := f.cache.GetOrInitCall(ctx, "filetree-session", srv,
		&dagql.CallRequest{ResultCall: call, IsPersistable: true}, dagql.ValueFunc(initial))
	require.NoError(t, err)
	first, ok := res.(dagql.ObjectResult[*Directory])
	require.True(t, ok)
	resultID, err := f.cache.PersistedResultID(first)
	require.NoError(t, err)
	wantLinks := []dagql.PersistedContentRefLink{{Role: "filetree", Digest: root.Digest}}
	links, err := f.cache.PersistedContentLinksByResultID(ctx, resultID)
	require.NoError(t, err)
	require.Equal(t, wantLinks, links)
	require.NoError(t, f.opts.LeaseManager.Delete(f.ctx, lease))
	f.gc(t)
	f.assertContent(t, root, child, blob, checksumObject)

	before, err := first.Self().EncodePersistedObject(ctx, f.cache)
	require.NoError(t, err)
	require.Equal(t, wantLinks, before.ContentLinks)
	require.Empty(t, before.SnapshotLinks)
	require.Empty(t, first.Self().PersistedSnapshotRefLinks())
	oldSnapshot := f.readDirectory(t, ctx, first, contents)
	require.Len(t, first.Self().PersistedSnapshotRefLinks(), 1)
	encoded, err := first.Self().EncodePersistedObject(ctx, f.cache)
	require.NoError(t, err)
	require.Equal(t, wantLinks, encoded.ContentLinks)
	require.Empty(t, encoded.SnapshotLinks, "derived views must not become mandatory persisted edges")
	var payload persistedDirectoryPayload
	require.NoError(t, json.Unmarshal(encoded.JSON, &payload))
	require.Equal(t, persistedDirectoryFormFileTree, payload.Form)
	require.Equal(t, root, payload.FileTree.Root)
	require.Equal(t, oldSnapshot, payload.FileTree.ViewHint)

	// A structurally valid descriptor is insufficient: the decoding result must
	// itself own that root. Never accept some other retained result's ownership.
	payload.FileTree.Root.Digest = digest.FromString("not-this-result-root")
	invalid, err := json.Marshal(payload)
	require.NoError(t, err)
	_, err = (&Directory{}).DecodePersistedObject(ctx, srv, resultID, call, invalid)
	require.ErrorContains(t, err, "filetree root lacks retained ownership")
	f.checkpoint(t, first)

	for _, materialize := range []bool{false, true} {
		f.restartManager(t)
		ctx, srv = f.openCache(t)
		require.Equal(t, dagql.CachePersistenceResetNone, f.cache.PersistenceResetReason())
		// Import's normal stale-owner reconciliation removes the old runtime
		// snapshot lease. No manual removal of result/content owners is needed.
		f.gc(t)
		_, err := f.sn.Stat(f.ctx, oldSnapshot)
		require.True(t, errdefs.IsNotFound(err), "old view must be collected: %v", err)
		var remaining []string
		require.NoError(t, f.sn.Walk(f.ctx, func(_ context.Context, info ctdsnapshots.Info) error {
			remaining = append(remaining, info.Name)
			return nil
		}))
		require.Empty(t, remaining, "CAS ownership must not retain derived snapshots")
		f.assertContent(t, root, child, blob, checksumObject)

		loaded, err := f.cache.GetOrInitCall(ctx, "filetree-session", srv,
			&dagql.CallRequest{ResultCall: call, IsPersistable: true},
			func(context.Context) (dagql.AnyResult, error) {
				return nil, errors.New("persisted CAS Directory unexpectedly replayed its initializer")
			})
		require.NoError(t, err)
		directory, ok := loaded.(dagql.ObjectResult[*Directory])
		require.True(t, ok)
		loadedID, err := f.cache.PersistedResultID(directory)
		require.NoError(t, err)
		require.Equal(t, resultID, loadedID)
		require.Equal(t, root, directory.Self().FileTree.Root)
		require.NotNil(t, directory.Self().Lazy)
		_, ready := directory.Self().Snapshot.Peek()
		require.False(t, ready, "decoding must not eagerly reconstruct a view")
		if materialize {
			newSnapshot := f.readDirectory(t, ctx, directory, contents)
			require.NotEqual(t, oldSnapshot, newSnapshot)
			require.Len(t, directory.Self().PersistedSnapshotRefLinks(), 1)
		}
		// First re-checkpoint remains unforced: an imported root must survive
		// another restart even when no accessor has materialized its view.
		f.checkpoint(t, directory)
	}
}

type directoryFileTreePersistenceFixture struct {
	ctx       context.Context
	root      string
	db        *metadata.DB
	sn        ctdsnapshots.Snapshotter
	opts      bkcache.SnapshotManagerOpt
	cm        bkcache.SnapshotManager
	cache     *dagql.Cache
	checksums map[string]digest.Digest
}

type persistedFileTreeChecksumInfo struct {
	*fsutil.StatInfo
	hash digest.Digest
}

func (info persistedFileTreeChecksumInfo) Digest() digest.Digest { return info.hash }

type fileTreePersistenceServer struct {
	*cacheVolumeTestQueryServer
	blobs content.Store
}

func (s *fileTreePersistenceServer) OCIStore() content.Store { return s.blobs }

func newDirectoryFileTreePersistenceFixture(t *testing.T) *directoryFileTreePersistenceFixture {
	t.Helper()
	root := t.TempDir()
	// Native's readonly view uses bind mounts. A private tmpfs gives this
	// privileged test a known writable backing filesystem with isolated cleanup.
	require.NoError(t, unix.Mount("tmpfs", root, "tmpfs", 0, "size=64m"))
	t.Cleanup(func() { require.NoError(t, unix.Unmount(root, 0)) })
	raw, err := native.NewSnapshotter(filepath.Join(root, "snapshots"))
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, raw.Close()) })
	cs, err := local.NewStore(filepath.Join(root, "content"))
	require.NoError(t, err)
	disk, err := bolt.Open(filepath.Join(root, "metadata.db"), 0o600, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, disk.Close()) })
	const namespace = "directory-filetree-persistence"
	f := &directoryFileTreePersistenceFixture{root: root, ctx: namespaces.WithNamespace(t.Context(), namespace)}
	f.db = metadata.NewDB(disk, cs, map[string]ctdsnapshots.Snapshotter{"native": raw})
	require.NoError(t, f.db.Init(f.ctx))
	f.sn = f.db.Snapshotter("native")
	f.opts = bkcache.SnapshotManagerOpt{
		Snapshotter:   bkcontainerd.NewSnapshotter("native", f.sn, namespace),
		ContentStore:  bkcontainerd.NewContentStore(f.db.ContentStore(), namespace),
		LeaseManager:  bkcache.NewLeaseManager(metadata.NewLeaseManager(f.db), namespace),
		MountPoolRoot: filepath.Join(root, "mounts"),
	}
	f.cm, err = bkcache.NewSnapshotManager(f.opts)
	require.NoError(t, err)
	t.Cleanup(func() {
		ctx := context.WithoutCancel(f.ctx)
		if f.cache != nil {
			require.NoError(t, f.cache.ReleaseSession(ctx, "filetree-session"))
			require.NoError(t, f.cache.Close(ctx))
		}
		require.NoError(t, f.cm.Close())
	})
	return f
}

func (f *directoryFileTreePersistenceFixture) openCache(t *testing.T) (context.Context, *dagql.Server) {
	t.Helper()
	require.Nil(t, f.cache)
	var err error
	f.cache, err = dagql.NewCache(f.ctx, filepath.Join(f.root, "dagql.db"), f.cm, nil)
	require.NoError(t, err)
	query := &Query{Server: &fileTreePersistenceServer{
		cacheVolumeTestQueryServer: &cacheVolumeTestQueryServer{mockServer: &mockServer{}, cacheManager: f.cm},
		blobs:                      f.opts.ContentStore,
	}}
	srv := newCoreDagqlServerForTest(t, query)
	srv.InstallObject(dagql.NewClass(srv, dagql.ClassOpts[*Directory]{}))
	return ContextWithQuery(dagql.ContextWithCache(f.ctx, f.cache), query), srv
}

func (f *directoryFileTreePersistenceFixture) checkpoint(t *testing.T, directory dagql.ObjectResult[*Directory]) {
	t.Helper()
	require.NoError(t, f.cache.ReleaseSession(f.ctx, "filetree-session"))
	require.NoError(t, f.cache.Close(f.ctx))
	f.cache = nil
	// Cache.Close checkpoints persistent roots rather than disposing their Go
	// values. Release the stopped process's accessor before discarding its manager.
	require.NoError(t, directory.Self().OnRelease(f.ctx))
}

func (f *directoryFileTreePersistenceFixture) restartManager(t *testing.T) {
	t.Helper()
	require.Nil(t, f.cache)
	require.NoError(t, f.cm.Close())
	var err error
	f.cm, err = bkcache.NewSnapshotManager(f.opts)
	require.NoError(t, err)
}

func (f *directoryFileTreePersistenceFixture) gc(t *testing.T) {
	t.Helper()
	_, err := f.db.GarbageCollect(f.ctx)
	require.NoError(t, err)
}

func (f *directoryFileTreePersistenceFixture) assertContent(t *testing.T, objects ...filetree.Object) {
	t.Helper()
	for _, obj := range objects {
		info, err := f.opts.ContentStore.Info(f.ctx, obj.Digest)
		require.NoError(t, err)
		require.Equal(t, obj.Size, info.Size)
	}
}

func (f *directoryFileTreePersistenceFixture) readDirectory(t *testing.T, ctx context.Context, directory dagql.ObjectResult[*Directory], contents string) string {
	t.Helper()
	ref, err := directory.Self().Snapshot.GetOrEval(ctx, directory.Result)
	require.NoError(t, err)
	rootDigest, err := directory.Self().Digest(ctx, directory)
	require.NoError(t, err)
	require.Equal(t, f.checksums["/"].String(), rootDigest)
	for name, want := range f.checksums {
		got, err := bkcontenthash.Checksum(ctx, ref, name, bkcontenthash.ChecksumOpts{})
		require.NoError(t, err)
		require.Equal(t, want, got, "public checksum after reconstruction: %s", name)
	}
	mountable, err := ref.Mount(ctx, true)
	require.NoError(t, err)
	mounter := bkcache.LocalMounter(mountable)
	root, err := mounter.Mount()
	require.NoError(t, err)
	defer func() { require.NoError(t, mounter.Unmount()) }()
	data, err := os.ReadFile(filepath.Join(root, "src", "lib.rs"))
	require.NoError(t, err)
	require.Equal(t, contents, string(data))
	file, err := os.Stat(filepath.Join(root, "src", "lib.rs"))
	require.NoError(t, err)
	alias, err := os.Stat(filepath.Join(root, "alias.rs"))
	require.NoError(t, err)
	require.True(t, os.SameFile(file, alias), "hardlink topology must survive view GC and cache restart")
	return ref.SnapshotID()
}
