package snapshots

import (
	"cmp"
	"context"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/metadata"
	"github.com/containerd/containerd/v2/pkg/namespaces"
	"github.com/containerd/containerd/v2/plugins/content/local"
	cerrdefs "github.com/containerd/errdefs"
	"github.com/dagger/dagger/engine/filetree"
	"github.com/moby/locker"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
)

type contentOwnerFixture struct {
	root string
	ctx  context.Context
	disk *bolt.DB
	db   *metadata.DB
	cm   *snapshotManager
	in   *filetree.Ingest
}

func newContentOwnerFixture(t *testing.T) *contentOwnerFixture {
	t.Helper()
	f := &contentOwnerFixture{root: t.TempDir(), ctx: namespaces.WithNamespace(t.Context(), "content-owner-test")}
	f.open(t)
	t.Cleanup(func() { require.NoError(t, f.disk.Close()) })
	_, err := f.cm.LeaseManager.Create(f.ctx, leases.WithID("operation"))
	require.NoError(t, err)
	f.in, err = filetree.NewStore(f.cm.ContentStore).Ingest(leases.WithLease(f.ctx, "operation"), f.cm.LeaseManager)
	require.NoError(t, err)
	return f
}

func (f *contentOwnerFixture) open(t *testing.T) {
	t.Helper()
	cs, err := local.NewStore(filepath.Join(f.root, "content"))
	require.NoError(t, err)
	f.disk, err = bolt.Open(filepath.Join(f.root, "metadata.db"), 0o600, nil)
	require.NoError(t, err)
	f.db = metadata.NewDB(f.disk, cs, nil)
	require.NoError(t, f.db.Init(f.ctx))
	f.cm = &snapshotManager{
		ContentStore: f.db.ContentStore(), LeaseManager: metadata.NewLeaseManager(f.db), ownerLeaseLocker: locker.New(),
	}
}

func (f *contentOwnerFixture) gc(t *testing.T) {
	t.Helper()
	_, err := f.db.GarbageCollect(f.ctx)
	require.NoError(t, err)
}

func (f *contentOwnerFixture) file(t *testing.T, data string) filetree.Object {
	t.Helper()
	obj, err := f.in.PutFile(strings.NewReader(data), int64(len(data)))
	require.NoError(t, err)
	return obj
}

func (f *contentOwnerFixture) tree(t *testing.T, entries ...filetree.Entry) filetree.Object {
	t.Helper()
	obj, err := f.in.PutTree(filetree.Tree{Version: filetree.TreeVersion, Entries: entries})
	require.NoError(t, err)
	return obj
}

func expectedContentUsage(objects ...filetree.Object) []ContentUsage {
	usage := make([]ContentUsage, 0, len(objects))
	for _, obj := range objects {
		usage = append(usage, ContentUsage{Digest: obj.Digest, Size: obj.Size})
	}
	slices.SortFunc(usage, func(a, b ContentUsage) int { return cmp.Compare(a.Digest, b.Digest) })
	return usage
}

func TestContentOwnershipNestedSharedGCAndRestart(t *testing.T) {
	f := newContentOwnerFixture(t)
	file := f.file(t, "shared Rust source")
	entry := filetree.Entry{Name: []byte("source.rs"), Kind: filetree.File, Metadata: &filetree.Metadata{Mode: 0o644}, Object: &file}
	first := f.tree(t, entry)
	entry.Metadata.Mode = 0o755
	second := f.tree(t, entry)
	root := f.tree(t,
		filetree.Entry{Name: []byte("a"), Kind: filetree.Directory, Object: &first},
		filetree.Entry{Name: []byte("b"), Kind: filetree.Directory, Object: &second},
		filetree.Entry{Name: []byte("c"), Kind: filetree.Directory, Object: &first},
	)
	owner := "dagql/result/1/content/tree/" + root.Digest.String()
	other := "dagql/result/2/content/tree/" + first.Digest.String()
	require.NoError(t, f.cm.AttachContentLease(f.ctx, owner, root.Digest))
	require.NoError(t, f.cm.AttachContentLease(f.ctx, other, first.Digest))
	resources, err := f.cm.LeaseManager.ListResources(f.ctx, leases.Lease{ID: owner})
	require.NoError(t, err)
	require.Equal(t, []leases.Resource{{Type: "content", ID: root.Digest.String()}}, resources)
	require.NoError(t, f.cm.LeaseManager.Delete(f.ctx, leases.Lease{ID: "operation"}))
	f.gc(t)
	usage, err := f.cm.ContentUsage(f.ctx, root.Digest)
	require.NoError(t, err)
	require.Equal(t, expectedContentUsage(root, first, second, file), usage)

	require.NoError(t, f.disk.Close())
	f.open(t)
	// Reattach is idempotent without source, snapshots or a new operation lease.
	require.NoError(t, f.cm.AttachContentLease(f.ctx, owner, root.Digest))
	f.gc(t)
	usage, err = f.cm.ContentUsage(f.ctx, root.Digest)
	require.NoError(t, err)
	require.Equal(t, expectedContentUsage(root, first, second, file), usage)
	require.NoError(t, f.cm.RemoveLease(f.ctx, owner))
	f.gc(t)
	for _, obj := range []filetree.Object{root, second} {
		_, err := f.cm.ContentStore.Info(f.ctx, obj.Digest)
		require.True(t, cerrdefs.IsNotFound(err), "%v", err)
	}
	usage, err = f.cm.ContentUsage(f.ctx, first.Digest)
	require.NoError(t, err)
	require.Equal(t, expectedContentUsage(first, file), usage)
	require.NoError(t, f.cm.RemoveLease(f.ctx, other))
	f.gc(t)
	for _, obj := range []filetree.Object{first, file} {
		_, err := f.cm.ContentStore.Info(f.ctx, obj.Digest)
		require.True(t, cerrdefs.IsNotFound(err), "%v", err)
	}
}

func TestContentOwnershipRejectsUnsafeExistingLease(t *testing.T) {
	f := newContentOwnerFixture(t)
	file := f.file(t, "owned")
	for _, tc := range []struct {
		name, label, value, errorText string
	}{
		{"flat", "containerd.io/gc.flat", "true", "must not be flat"},
		{"expiring", "containerd.io/gc.expire", time.Now().Add(time.Hour).UTC().Format(time.RFC3339Nano), "must not expire"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			_, err := f.cm.LeaseManager.Create(f.ctx, leases.WithID(tc.name), leases.WithLabel(tc.label, tc.value))
			require.NoError(t, err)
			require.ErrorContains(t, f.cm.AttachContentLease(f.ctx, tc.name, file.Digest), tc.errorText)
			matches, err := f.cm.LeaseManager.List(f.ctx, "id=="+tc.name)
			require.NoError(t, err)
			require.Len(t, matches, 1, "must preserve the existing lease")
			require.Equal(t, tc.value, matches[0].Labels[tc.label])
			resources, err := f.cm.LeaseManager.ListResources(f.ctx, matches[0])
			require.NoError(t, err)
			require.Empty(t, resources)
		})
	}

	require.NoError(t, f.cm.AttachContentLease(f.ctx, "existing", file.Digest))
	require.ErrorContains(t, f.cm.AttachContentLease(f.ctx, "existing", digest.FromString("different")), "different resource")
	resources, err := f.cm.LeaseManager.ListResources(f.ctx, leases.Lease{ID: "existing"})
	require.NoError(t, err)
	require.Equal(t, []leases.Resource{{Type: "content", ID: file.Digest.String()}}, resources)
}

func TestContentOwnershipMissingRootCleanup(t *testing.T) {
	f := newContentOwnerFixture(t)
	missing := digest.FromString("missing")
	err := f.cm.AttachContentLease(f.ctx, "new-owner", missing)
	require.True(t, cerrdefs.IsNotFound(err), "%v", err)
	matches, err := f.cm.LeaseManager.List(f.ctx, "id==new-owner")
	require.NoError(t, err)
	require.Empty(t, matches, "new failed lease must not remain")

	_, err = f.cm.LeaseManager.Create(f.ctx, leases.WithID("empty-existing"))
	require.NoError(t, err)
	err = f.cm.AttachContentLease(f.ctx, "empty-existing", missing)
	require.True(t, cerrdefs.IsNotFound(err), "%v", err)
	matches, err = f.cm.LeaseManager.List(f.ctx, "id==empty-existing")
	require.NoError(t, err)
	require.Len(t, matches, 1, "pre-existing lease must remain")
	resources, err := f.cm.LeaseManager.ListResources(f.ctx, matches[0])
	require.NoError(t, err)
	require.Empty(t, resources, "failed new resource must be rolled back")
	require.Error(t, f.cm.AttachContentLease(f.ctx, "", missing))
	require.Error(t, f.cm.AttachContentLease(f.ctx, "invalid", "not-a-digest"))
}

func TestContentUsageLabelSemanticsAndCycles(t *testing.T) {
	f := newContentOwnerFixture(t)
	root, child := f.file(t, "root"), f.file(t, "child")
	labels := map[string]string{
		"containerd.io/gc.ref.content":       child.Digest.String(),
		"containerd.io/gc.ref.content.named": child.Digest.String(),
		"containerd.io/gc.ref.content/self":  root.Digest.String(),
		"containerd.io/gc.ref.contentish":    "not-a-digest",
	}
	_, err := f.cm.ContentStore.Update(f.ctx, content.Info{Digest: root.Digest, Labels: labels}, "labels")
	require.NoError(t, err)
	usage, err := f.cm.ContentUsage(f.ctx, root.Digest)
	require.NoError(t, err)
	require.Equal(t, expectedContentUsage(root, child), usage)

	for _, target := range []string{"invalid", digest.FromString("missing-child").String()} {
		_, err := f.cm.ContentStore.Update(f.ctx, content.Info{Digest: root.Digest, Labels: map[string]string{
			"containerd.io/gc.ref.content.bad": target,
		}}, "labels.containerd.io/gc.ref.content.bad")
		require.NoError(t, err)
		usage, err := f.cm.ContentUsage(f.ctx, root.Digest)
		require.Error(t, err)
		require.Nil(t, usage, "must not return an incomplete usage estimate")
	}
	_, err = f.cm.ContentUsage(f.ctx, digest.FromString("missing-root"))
	require.True(t, cerrdefs.IsNotFound(err), "%v", err)
	_, err = f.cm.ContentUsage(f.ctx, "bad")
	require.Error(t, err)
}

func TestContentOwnershipCancellation(t *testing.T) {
	f := newContentOwnerFixture(t)
	file := f.file(t, "retained")
	ctx, cancel := context.WithCancel(f.ctx)
	cancel()
	require.ErrorIs(t, f.cm.AttachContentLease(ctx, "canceled", file.Digest), context.Canceled)
	usage, err := f.cm.ContentUsage(ctx, file.Digest)
	require.ErrorIs(t, err, context.Canceled)
	require.Nil(t, usage)
	matches, err := f.cm.LeaseManager.List(f.ctx, "id==canceled")
	require.NoError(t, err)
	require.Empty(t, matches)
}
