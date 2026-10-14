package contenthash

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"testing"

	ctdmount "github.com/containerd/containerd/v2/core/mount"
	cache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/internal/fsutil"
	digest "github.com/opencontainers/go-digest"
	"github.com/pkg/errors"
	"gotest.tools/v3/assert"
)

func TestFileWritePreservesImportedSiblingHashes(t *testing.T) {
	for _, name := range []string{"existing", "new file", "new directories", "partial context"} {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			parentRoot, childRoot := t.TempDir(), t.TempDir()
			for _, root := range []string{parentRoot, childRoot} {
				writeFile(t, root, "base/lib.rs", "base")
				writeFile(t, root, "app/lib.rs", "before")
			}
			source := &copyTestMetadata{id: t.Name() + "/source"}
			destination := &copyTestMetadata{id: t.Name() + "/destination"}
			parent, err := getDefaultManager().GetCacheContext(ctx, source)
			assert.NilError(t, err)
			if name != "partial context" {
				_, err = parent.Checksum(ctx, bindMountable{parentRoot}, "/", ChecksumOpts{})
				assert.NilError(t, err)
			}
			selected := "/base"
			if name == "partial context" {
				selected = "/base/lib.rs"
				_, err = parent.Checksum(ctx, bindMountable{parentRoot}, selected, ChecksumOpts{})
				assert.NilError(t, err)
				cc := parent.(*cacheContext)
				cc.mu.Lock()
				txn := cc.tree.Txn()
				txn.Insert(convertPathToKey(selected), &CacheRecord{Type: CacheRecordTypeFile, Digest: "xxh3:0000000000000001"})
				cc.tree = txn.Commit()
				cc.mu.Unlock()
			} else {
				stat, err := fsutil.Stat(filepath.Join(parentRoot, "base/lib.rs"))
				assert.NilError(t, err)
				assert.NilError(t, parent.HandleChange(fsutil.ChangeKindModify, "/base/lib.rs", &copyTestFileInfo{statInfo: &statInfo{stat}, dgst: "xxh3:0000000000000001"}, nil))
			}
			want, err := parent.Checksum(ctx, bindMountable{parentRoot}, selected, ChecksumOpts{})
			assert.NilError(t, err)
			if name == "existing" {
				// Copy a context with an uncommitted import transaction.
				stat, err := fsutil.Stat(filepath.Join(parentRoot, "base/lib.rs"))
				assert.NilError(t, err)
				assert.NilError(t, parent.HandleChange(fsutil.ChangeKindModify, "/base/lib.rs", &copyTestFileInfo{statInfo: &statInfo{stat}, dgst: "xxh3:0000000000000001"}, nil))
			}
			filename := "/app/lib.rs"
			var created []string
			switch name {
			case "new file":
				filename = "/app/new.rs"
			case "new directories":
				filename = "/new/deep/new.rs"
				created = []string{"/new/deep", "/new"}
			}
			writeFile(t, childRoot, filename, "after")
			assert.NilError(t, CopyCacheContextForFileWrite(ctx, source, destination, filename, created))
			// The inherited records must survive dropping the in-memory context.
			ClearCacheContext(destination)
			child, err := getDefaultManager().GetCacheContext(ctx, destination)
			assert.NilError(t, err)
			got, err := child.Checksum(ctx, bindMountable{childRoot}, selected, ChecksumOpts{})
			assert.NilError(t, err)
			assert.Equal(t, got, want)
			changed, err := child.Checksum(ctx, bindMountable{childRoot}, filename, ChecksumOpts{})
			assert.NilError(t, err)
			fresh, err := newTestCacheContext(t).Checksum(ctx, bindMountable{childRoot}, filename, ChecksumOpts{})
			assert.NilError(t, err)
			assert.Equal(t, changed, fresh, "the written file must use its current contents")
			_, err = child.Checksum(ctx, bindMountable{childRoot}, "/", ChecksumOpts{})
			assert.NilError(t, err)
			old, err := parent.Checksum(ctx, bindMountable{parentRoot}, "/app/lib.rs", ChecksumOpts{})
			assert.NilError(t, err)
			original, err := newTestCacheContext(t).Checksum(ctx, bindMountable{parentRoot}, "/app/lib.rs", ChecksumOpts{})
			assert.NilError(t, err)
			assert.Equal(t, old, original, "copying records must not change the parent")
		})
	}
}

func TestConcurrentFileWriteContexts(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()
	writeFile(t, root, "base/lib.rs", "base")
	writeFile(t, root, "app/lib.rs", "before")
	source := &copyTestMetadata{id: t.Name() + "/source"}
	parent, err := getDefaultManager().GetCacheContext(ctx, source)
	assert.NilError(t, err)
	before, err := parent.Checksum(ctx, bindMountable{root}, "/app/lib.rs", ChecksumOpts{})
	assert.NilError(t, err)
	for i := range 8 {
		t.Run(fmt.Sprint(i), func(t *testing.T) {
			t.Parallel()
			childRoot := t.TempDir()
			contents := fmt.Sprint(i)
			writeFile(t, childRoot, "base/lib.rs", "base")
			writeFile(t, childRoot, "app/lib.rs", contents)
			destination := &copyTestMetadata{id: t.Name() + "/destination"}
			assert.NilError(t, CopyCacheContextForFileWrite(ctx, source, destination, "/app/lib.rs", nil))
			child, err := getDefaultManager().GetCacheContext(ctx, destination)
			assert.NilError(t, err)
			got, err := child.Checksum(ctx, bindMountable{childRoot}, "/app/lib.rs", ChecksumOpts{})
			assert.NilError(t, err)
			want, err := newTestCacheContext(t).Checksum(ctx, bindMountable{childRoot}, "/app/lib.rs", ChecksumOpts{})
			assert.NilError(t, err)
			assert.Equal(t, got, want, "concurrent children must keep their own written file")
			unchanged, err := parent.Checksum(ctx, bindMountable{root}, "/app/lib.rs", ChecksumOpts{})
			assert.NilError(t, err)
			assert.Equal(t, unchanged, before, "concurrent writes must not change the parent's tree")
		})
	}
}

type copyTestFileInfo struct {
	*statInfo
	dgst digest.Digest
}

func (fi *copyTestFileInfo) Digest() digest.Digest { return fi.dgst }

type copyTestMetadata struct {
	testRefMetadata
	id   string
	mu   sync.Mutex
	data []byte
}

func (md *copyTestMetadata) ID() string { return md.id }
func (md *copyTestMetadata) GetExternal(string) ([]byte, error) {
	md.mu.Lock()
	defer md.mu.Unlock()
	return append([]byte(nil), md.data...), nil
}
func (md *copyTestMetadata) SetExternal(_ string, data []byte) error {
	md.mu.Lock()
	defer md.mu.Unlock()
	md.data = append([]byte(nil), data...)
	return nil
}

// Checksumming a file must not walk its parent directory: for a file at the
// root of a container filesystem that is a walk of the whole filesystem.
// Recording only the file must not change any digest, including the digests
// of directories checksummed later from the same cache context.
func TestChecksumFileDoesNotWalkParent(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()
	writeFile(t, root, "stamp", "stamp")
	writeFile(t, root, "work/b001/b001.a", "archive")
	for i := range 100 {
		writeFile(t, root, fmt.Sprintf("usr/lib/f%d", i), "lib")
	}
	assert.NilError(t, os.Symlink("stamp", filepath.Join(root, "link")))
	mnt := bindMountable{root}

	// Reference digests from a context that walked the whole tree first.
	full := newTestCacheContext(t)
	want := map[string]digest.Digest{}
	for _, p := range []string{"/", "/stamp", "/link", "/work", "/work/b001/b001.a", "/usr/lib/f7"} {
		dgst, err := full.Checksum(ctx, mnt, p, ChecksumOpts{FollowLinks: true})
		assert.NilError(t, err)
		want[p] = dgst
	}
	linkNoFollow, err := full.Checksum(ctx, mnt, "/link", ChecksumOpts{})
	assert.NilError(t, err)

	scanCounterEnable = true
	t.Cleanup(func() { scanCounterEnable = false })

	cc := newTestCacheContext(t)
	for _, p := range []string{"/stamp", "/link", "/work/b001/b001.a"} {
		scanCounter.Store(0)
		dgst, err := cc.Checksum(ctx, mnt, p, ChecksumOpts{FollowLinks: true})
		assert.NilError(t, err)
		assert.Equal(t, dgst, want[p], p)
		assert.Assert(t, scanCounter.Load() <= 1, "%s: scanned %d entries", p, scanCounter.Load())
	}
	dgst, err := cc.Checksum(ctx, mnt, "/link", ChecksumOpts{})
	assert.NilError(t, err)
	assert.Equal(t, dgst, linkNoFollow)

	// Directories and siblings checksummed after the file-only records still
	// get the digests of a full walk.
	for _, p := range []string{"/work", "/usr/lib/f7", "/"} {
		dgst, err := cc.Checksum(ctx, mnt, p, ChecksumOpts{FollowLinks: true})
		assert.NilError(t, err)
		assert.Equal(t, dgst, want[p], p)
	}

	_, err = newTestCacheContext(t).Checksum(ctx, mnt, "/missing", ChecksumOpts{FollowLinks: true})
	assert.Assert(t, errors.Is(err, errNotFound), "got %v", err)
	_, err = newTestCacheContext(t).Checksum(ctx, mnt, "/stamp/missing", ChecksumOpts{FollowLinks: true})
	assert.Assert(t, err != nil)
}

func writeFile(t *testing.T, root, p, contents string) {
	t.Helper()
	fp := filepath.Join(root, p)
	assert.NilError(t, os.MkdirAll(filepath.Dir(fp), 0o755))
	assert.NilError(t, os.WriteFile(fp, []byte(contents), 0o644))
}

func newTestCacheContext(t *testing.T) *cacheContext {
	t.Helper()
	cc, err := newCacheContext(testRefMetadata{})
	assert.NilError(t, err)
	return cc
}

// testRefMetadata stores nothing; the cache context only reads and writes its
// serialized tree through it.
type testRefMetadata struct {
	cache.RefMetadata
}

func (testRefMetadata) GetExternal(string) ([]byte, error) {
	return nil, errors.New("not found")
}

func (testRefMetadata) SetExternal(string, []byte) error {
	return nil
}

// bindMountable mounts a host directory. A writable bind mount is used as is,
// so no mount is performed.
type bindMountable struct {
	dir string
}

func (m bindMountable) Mount(context.Context, bool) (cache.MountableRef, error) {
	return bindMounts(m), nil
}

type bindMounts bindMountable

func (m bindMounts) Mount() ([]ctdmount.Mount, func() error, error) {
	return []ctdmount.Mount{{Type: "bind", Source: m.dir, Options: []string{"rbind"}}}, func() error { return nil }, nil
}
