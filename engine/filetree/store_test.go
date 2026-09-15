package filetree

import (
	"bytes"
	"context"
	"errors"
	"io"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/containerd/containerd/v2/core/content"
	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/metadata"
	"github.com/containerd/containerd/v2/pkg/namespaces"
	"github.com/containerd/containerd/v2/plugins/content/local"
	"github.com/containerd/errdefs"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	bolt "go.etcd.io/bbolt"
)

// Exercise real containerd metadata, content and garbage collection, not a map
// that assumes referenced children survive. No snapshots or mounts are needed.
type testStore struct {
	root  string
	ctx   context.Context
	disk  *bolt.DB
	db    *metadata.DB
	lm    leases.Manager
	store *Store
}

func newTestStore(t *testing.T) *testStore {
	t.Helper()
	f := &testStore{root: t.TempDir(), ctx: namespaces.WithNamespace(t.Context(), "filetree-test")}
	f.open(t)
	t.Cleanup(func() { require.NoError(t, f.disk.Close()) })
	return f
}

func (f *testStore) open(t *testing.T) {
	t.Helper()
	cs, err := local.NewStore(filepath.Join(f.root, "content"))
	require.NoError(t, err)
	f.disk, err = bolt.Open(filepath.Join(f.root, "metadata.db"), 0o600, nil)
	require.NoError(t, err)
	f.db = metadata.NewDB(f.disk, cs, nil)
	require.NoError(t, f.db.Init(f.ctx))
	f.lm = metadata.NewLeaseManager(f.db)
	f.store = NewStore(f.db.ContentStore())
}

func (f *testStore) ingest(t *testing.T, id string) *Ingest {
	t.Helper()
	_, err := f.lm.Create(f.ctx, leases.WithID(id))
	require.NoError(t, err)
	in, err := f.store.Ingest(leases.WithLease(f.ctx, id), f.lm)
	require.NoError(t, err)
	return in
}

func (f *testStore) gc(t *testing.T) {
	t.Helper()
	_, err := f.db.GarbageCollect(f.ctx)
	require.NoError(t, err)
}

func (f *testStore) readFile(t *testing.T, obj Object) []byte {
	t.Helper()
	r, err := f.store.OpenFile(f.ctx, obj)
	require.NoError(t, err)
	data, err := io.ReadAll(content.NewReader(r))
	require.NoError(t, errors.Join(err, r.Close()))
	return data
}

func fileTree(file Object) Tree {
	return Tree{Version: TreeVersion, Metadata: Metadata{Mode: 0o755}, Entries: []Entry{{
		Name: []byte("source.rs"), Kind: File, Metadata: &Metadata{Mode: 0o644}, Object: &file,
	}}}
}

func TestStoreFileRoundTrip(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "write")
	for _, data := range []string{"", "fn main() {}", strings.Repeat("not-a-whole-file-buffer", 1<<17)} {
		obj, err := in.PutFile(strings.NewReader(data), int64(len(data)))
		require.NoError(t, err)
		require.Equal(t, Object{Digest: digest.FromString(data), Size: int64(len(data))}, obj)
		require.Equal(t, []byte(data), f.readFile(t, obj))
	}
}

func TestStoreRequiresNonFlatLease(t *testing.T) {
	f := newTestStore(t)
	_, err := f.store.Ingest(f.ctx, f.lm)
	require.ErrorContains(t, err, "requires an operation lease")
	_, err = f.store.Ingest(leases.WithLease(f.ctx, "missing"), f.lm)
	require.ErrorContains(t, err, "is missing")
	_, err = f.lm.Create(f.ctx, leases.WithID("flat"), leases.WithLabel("containerd.io/gc.flat", "true"))
	require.NoError(t, err)
	_, err = f.store.Ingest(leases.WithLease(f.ctx, "flat"), f.lm)
	require.ErrorContains(t, err, "non-flat")
}

func TestStoreRejectsPartialWrites(t *testing.T) {
	for _, tc := range []struct {
		name, data string
		size       int64
	}{
		{"short", "partial", 8},
		{"long", "partial", 6},
		{"not-empty", "x", 0},
		{"negative", "", -1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := newTestStore(t)
			in := f.ingest(t, "write")
			_, err := in.PutFile(strings.NewReader(tc.data), tc.size)
			require.Error(t, err)
			statuses, err := f.store.blobs.ListStatuses(f.ctx)
			require.NoError(t, err)
			require.Empty(t, statuses, "abandoned ingestion must be aborted")
			var committed []content.Info
			require.NoError(t, f.store.blobs.Walk(f.ctx, func(info content.Info) error {
				committed = append(committed, info)
				return nil
			}))
			require.Empty(t, committed)
		})
	}
}

func TestStoreCancellationAbortsIngest(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "cancel")
	ctx, cancel := context.WithCancel(in.ctx)
	in.ctx = ctx
	r := &cancelReader{cancel: cancel}
	_, err := in.PutFile(r, 1024)
	require.ErrorIs(t, err, context.Canceled)
	statuses, err := f.store.blobs.ListStatuses(f.ctx)
	require.NoError(t, err)
	require.Empty(t, statuses)
}

type cancelReader struct{ cancel context.CancelFunc }

func (r *cancelReader) Read(p []byte) (int, error) {
	p[0] = 'x'
	r.cancel()
	return 1, nil
}

func TestStoreMissingChildDoesNotPublishTree(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "write")
	tree := fileTree(*testObject("absent"))
	_, err := in.PutTree(tree)
	require.Error(t, err)
	_, err = f.store.blobs.Info(f.ctx, digest.FromBytes(mustEncode(t, tree)))
	require.True(t, errdefs.IsNotFound(err), "%v", err)
}

func TestStoreTreeCannotReferenceRawFileAsDirectory(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "write")
	data := mustEncode(t, Tree{Version: TreeVersion})
	file, err := in.PutFile(bytes.NewReader(data), int64(len(data)))
	require.NoError(t, err)
	_, err = in.PutTree(Tree{Version: TreeVersion, Entries: []Entry{{Name: []byte("d"), Kind: Directory, Object: &file}}})
	require.ErrorContains(t, err, "incomplete GC links")
}

func TestStoreRepairsAlreadyPresentTreeLinks(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "write")
	file, err := in.PutFile(strings.NewReader("source"), 6)
	require.NoError(t, err)
	tree := fileTree(file)
	data := mustEncode(t, tree)
	raw, err := in.PutFile(bytes.NewReader(data), int64(len(data)))
	require.NoError(t, err)
	_, err = f.store.blobs.Update(f.ctx, content.Info{Digest: raw.Digest, Labels: map[string]string{"unrelated": "preserved"}}, "labels.unrelated")
	require.NoError(t, err)
	root, err := in.PutTree(tree)
	require.NoError(t, err)
	require.Equal(t, raw, root)
	_, err = f.store.ReadTree(f.ctx, root)
	require.NoError(t, err)
	info, err := f.store.blobs.Info(f.ctx, root.Digest)
	require.NoError(t, err)
	require.Equal(t, "preserved", info.Labels["unrelated"])
}

func TestStoreReusesTreeBytesFromAnotherNamespace(t *testing.T) {
	f := newTestStore(t)
	tree := Tree{Version: TreeVersion}
	data := mustEncode(t, tree)
	other := namespaces.WithNamespace(f.ctx, "another-namespace")
	_, err := f.lm.Create(other, leases.WithID("other"))
	require.NoError(t, err)
	in, err := f.store.Ingest(leases.WithLease(other, "other"), f.lm)
	require.NoError(t, err)
	file, err := in.PutFile(bytes.NewReader(data), int64(len(data)))
	require.NoError(t, err)
	// The physical bytes exist, but not in this namespace. Containerd reuses
	// them through a writer whose initial offset is already the full size.
	root, err := f.ingest(t, "write").PutTree(tree)
	require.NoError(t, err)
	require.Equal(t, file, root)
	_, err = f.store.ReadTree(f.ctx, root)
	require.NoError(t, err)
}

func TestTreeBudgetPreflight(t *testing.T) {
	// Small budgets exercise rejection before cloning/marshalling without
	// allocating deliberately huge trees in the test runner.
	require.NoError(t, checkTreeBudget(Tree{Version: TreeVersion}, 48))
	require.Error(t, checkTreeBudget(Tree{Version: TreeVersion}, 47))
	tree := fileTree(*testObject("content"))
	require.NoError(t, checkTreeBudget(tree, len(mustEncode(t, tree))))
	require.Error(t, checkTreeBudget(tree, 64))
	tree = Tree{Version: TreeVersion, Metadata: Metadata{Xattrs: []Xattr{{
		Name: []byte("user.large"), Value: make([]byte, 128),
	}}}}
	require.Error(t, checkTreeBudget(tree, 128))
	require.Error(t, checkTreeBudget(tree, -1))
	// Every valid encoding within the exact limit must also fit the lower
	// bound, including directories with many object references.
	tree = fileTree(*testObject("content"))
	for i := range 100 {
		entry := tree.Entries[0]
		entry.Name = []byte(strings.Repeat("n", i+1))
		tree.Entries = append(tree.Entries, entry)
	}
	require.NoError(t, checkTreeBudget(tree, len(mustEncode(t, tree))))
}

func TestStoreRejectsWrongExpectedDigest(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "write")
	expected := digest.FromString("right")
	_, err := in.put(strings.NewReader("wrong"), 5, expected, nil)
	require.Error(t, err)
	_, err = f.store.blobs.Info(f.ctx, expected)
	require.True(t, errdefs.IsNotFound(err), "%v", err)
	statuses, err := f.store.blobs.ListStatuses(f.ctx)
	require.NoError(t, err)
	require.Empty(t, statuses)
}

func TestStoreRootRetainsClosureAcrossRestart(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "operation")
	file, err := in.PutFile(strings.NewReader("fn main() {}"), 12)
	require.NoError(t, err)
	child, err := in.PutTree(fileTree(file))
	require.NoError(t, err)
	root, err := in.PutTree(Tree{Version: TreeVersion, Entries: []Entry{{Name: []byte("src"), Kind: Directory, Object: &child}}})
	require.NoError(t, err)
	owner := f.ingest(t, "result")
	require.NoError(t, owner.Retain(root))
	resources, err := f.lm.ListResources(f.ctx, owner.lease)
	require.NoError(t, err)
	require.Equal(t, []leases.Resource{{Type: "content", ID: root.Digest.String()}}, resources)
	require.NoError(t, f.lm.Delete(f.ctx, in.lease))
	f.gc(t)
	// Reopen the actual content and metadata stores, without any source or
	// snapshot. The result lease, root and outgoing links all live on disk.
	require.NoError(t, f.disk.Close())
	f.open(t)
	f.gc(t)
	for _, obj := range []Object{root, child} {
		_, err := f.store.ReadTree(f.ctx, obj)
		require.NoError(t, err)
	}
	require.Equal(t, []byte("fn main() {}"), f.readFile(t, file))
	require.NoError(t, f.lm.Delete(f.ctx, owner.lease))
	f.gc(t)
	for _, obj := range []Object{root, child, file} {
		_, err := f.store.blobs.Info(f.ctx, obj.Digest)
		require.True(t, errdefs.IsNotFound(err), "%s: %v", obj.Digest, err)
	}
}

func TestStoreSharedBlobSurvivesOneOwnerPruned(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "operation")
	file, err := in.PutFile(strings.NewReader("shared"), 6)
	require.NoError(t, err)
	tree := fileTree(file)
	first, err := in.PutTree(tree)
	require.NoError(t, err)
	tree.Entries[0].Metadata.Mode = 0o755
	second, err := in.PutTree(tree)
	require.NoError(t, err)
	require.NotEqual(t, first.Digest, second.Digest)
	one, two := f.ingest(t, "one"), f.ingest(t, "two")
	require.NoError(t, one.Retain(first))
	require.NoError(t, two.Retain(second))
	require.NoError(t, f.lm.Delete(f.ctx, in.lease))
	require.NoError(t, f.lm.Delete(f.ctx, one.lease))
	f.gc(t)
	_, err = f.store.blobs.Info(f.ctx, first.Digest)
	require.True(t, errdefs.IsNotFound(err), "%v", err)
	_, err = f.store.ReadTree(f.ctx, second)
	require.NoError(t, err)
	require.Equal(t, []byte("shared"), f.readFile(t, file))
}

func TestStoreConcurrentDuplicateWrites(t *testing.T) {
	f := newTestStore(t)
	in := f.ingest(t, "operation")
	var wg sync.WaitGroup
	for range 8 {
		wg.Go(func() {
			file, err := in.PutFile(strings.NewReader("shared"), 6)
			if err == nil {
				_, err = in.PutTree(fileTree(file))
			}
			if err != nil {
				t.Error(err)
			}
		})
	}
	wg.Wait()
	var committed []content.Info
	require.NoError(t, f.store.blobs.Walk(f.ctx, func(info content.Info) error {
		committed = append(committed, info)
		return nil
	}))
	require.Len(t, committed, 2, "one file and one directory node")
	statuses, err := f.store.blobs.ListStatuses(f.ctx)
	require.NoError(t, err)
	require.Empty(t, statuses)
}
