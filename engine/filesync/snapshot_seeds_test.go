package filesync

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"

	contenthash "github.com/dagger/dagger/engine/contenthash"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/snapshots/testutil"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/util/fsxutil"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

// Compare real imported files with a full copy in an independent snapshot
// store, so content-hash lookup cannot make the oracle reuse the candidate.
func TestSyncSnapshotSeeds(t *testing.T) {
	clientRoot := writeTree(t, map[string]string{"src/lib.rs": "initial", "keep.txt": "keep"})
	client, err := fsutil.NewFS(clientRoot)
	assert.NilError(t, err)
	seededStore, fullStore := testutil.NewStore(t), testutil.NewStore(t)
	seededMirror, fullMirror := t.TempDir(), t.TempDir()
	seeds := &SnapshotSeeds{}
	var original bkcache.ImmutableRef
	var originalTree map[string]seedTestEntry
	for i := range 2*maxSnapshotSeedDepth + 3 {
		assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, "src/lib.rs"), []byte(strings.Repeat("edit", i+1)), 0o644))
		// A new shared runtime per call matches ClientFilesyncMirror releasing
		// its mounted runtime between ordinary CLI commands.
		local, err := newLocalFS(NewMirrorSharedState(seededMirror), "", nil, nil, nil, "")
		assert.NilError(t, err)
		local.seeds, local.seedScope = seeds, "workspace"
		full, err := newLocalFS(NewMirrorSharedState(fullMirror), "", nil, nil, nil, "")
		assert.NilError(t, err)
		candidate, candidateOwner := syncPublished(t, seededStore, local, client)
		oracle, oracleOwner := syncPublished(t, fullStore, full, client)
		assert.Assert(t, is.DeepEqual(seedTestTree(t, testutil.Root(t, candidate)), seedTestTree(t, testutil.Root(t, oracle))), "edit %d", i)
		seed, ok := seeds.get("workspace")
		assert.Assert(t, ok, "edit %d did not retain a seed", i)
		assert.Equal(t, seed.id, candidate.SnapshotID())
		assert.Equal(t, seed.depth, i%(maxSnapshotSeedDepth+1))
		assert.Equal(t, seedParentDepth(t, seededStore.Manager, candidate.SnapshotID()), seed.depth)
		seedAssertDigest(t, candidate, oracle)
		if original == nil {
			original, originalTree = candidate, seedTestTree(t, testutil.Root(t, candidate))
		} else {
			assert.Assert(t, is.DeepEqual(seedTestTree(t, testutil.Root(t, original)), originalTree), "edit %d changed the original snapshot", i)
		}
		t.Cleanup(func() {
			assert.NilError(t, candidate.Release(context.Background()))
			assert.NilError(t, seededStore.Manager.RemoveLease(context.Background(), candidateOwner))
			assert.NilError(t, oracle.Release(context.Background()))
			assert.NilError(t, fullStore.Manager.RemoveLease(context.Background(), oracleOwner))
		})
	}
}

func TestSyncSnapshotSeedsMirrorChangesAndFallbacks(t *testing.T) {
	clientRoot := writeTree(t, map[string]string{"src/lib.rs": "initial", "keep.txt": "keep"})
	client, err := fsutil.NewFS(clientRoot)
	assert.NilError(t, err)
	store, fullStore := testutil.NewStore(t), testutil.NewStore(t)
	mirrorRoot, fullMirror := t.TempDir(), t.TempDir()
	seeds := &SnapshotSeeds{}
	newLocal := func(includes []string, scope string) *localFS {
		t.Helper()
		local, err := newLocalFS(NewMirrorSharedState(mirrorRoot), "", includes, nil, nil, "")
		assert.NilError(t, err)
		local.seeds, local.seedScope = seeds, scope
		return local
	}
	compare := func(t *testing.T) snapshotSeed {
		t.Helper()
		local := newLocal(nil, "workspace")
		full, err := newLocalFS(NewMirrorSharedState(fullMirror), "", nil, nil, nil, "")
		assert.NilError(t, err)
		candidate, candidateOwner := syncPublished(t, store, local, client)
		oracle, oracleOwner := syncPublished(t, fullStore, full, client)
		assert.Assert(t, is.DeepEqual(seedTestTree(t, testutil.Root(t, candidate)), seedTestTree(t, testutil.Root(t, oracle))))
		seedAssertDigest(t, candidate, oracle)
		t.Cleanup(func() {
			assert.NilError(t, candidate.Release(context.Background()))
			assert.NilError(t, store.Manager.RemoveLease(context.Background(), candidateOwner))
			assert.NilError(t, oracle.Release(context.Background()))
			assert.NilError(t, fullStore.Manager.RemoveLease(context.Background(), oracleOwner))
		})
		seed, ok := seeds.get("workspace")
		assert.Assert(t, ok)
		return seed
	}
	compare(t)
	t.Run("intervening filter", func(t *testing.T) {
		assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, "keep.txt"), []byte("updated by another projection"), 0o644))
		filtered, err := fsutil.NewFilterFS(client, &fsutil.FilterOpt{IncludePatterns: []string{"keep.txt"}})
		assert.NilError(t, err)
		local := newLocal([]string{"keep.txt"}, "narrow")
		ref, owner := syncPublished(t, store, local, filtered)
		defer ref.Release(context.Background())
		defer store.Manager.RemoveLease(context.Background(), owner)
		assert.Equal(t, compare(t).depth, 1)
	})
	t.Run("failed commit", func(t *testing.T) {
		before, _ := seeds.get("workspace")
		assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, "src/lib.rs"), []byte("written to the mirror before publication fails"), 0o644))
		ctx, release, err := bkcache.WithLazyLease(context.Background(), store.Leases, bkcache.MakeTemporary)
		assert.NilError(t, err)
		defer release(context.Background())
		_, _, err = newLocal(nil, "workspace").Sync(ctx, readFS{client}, seedFailCommitManager{store.Manager}, false)
		assert.Assert(t, errors.Is(err, errSeedCommit))
		after, _ := seeds.get("workspace")
		assert.Equal(t, after.id, before.id)
		assert.Equal(t, compare(t).depth, before.depth+1)
	})
	t.Run("add nested file", func(t *testing.T) {
		assert.NilError(t, os.MkdirAll(filepath.Join(clientRoot, "new/sub"), 0o751))
		assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, "new/sub/file"), []byte("new"), 0o640))
		compare(t)
	})
	t.Run("permissions", func(t *testing.T) {
		assert.NilError(t, os.Chmod(filepath.Join(clientRoot, "src"), 0o751))
		assert.NilError(t, os.Chmod(filepath.Join(clientRoot, "src/lib.rs"), 0o640))
		compare(t)
	})
	t.Run("delete directory", func(t *testing.T) {
		assert.NilError(t, os.RemoveAll(filepath.Join(clientRoot, "new")))
		assert.Equal(t, compare(t).depth, 0)
	})
	t.Run("file to directory", func(t *testing.T) {
		assert.NilError(t, os.Remove(filepath.Join(clientRoot, "keep.txt")))
		assert.NilError(t, os.Mkdir(filepath.Join(clientRoot, "keep.txt"), 0o755))
		assert.Equal(t, compare(t).depth, 0)
	})
	t.Run("symlink", func(t *testing.T) {
		assert.NilError(t, os.Symlink("src/lib.rs", filepath.Join(clientRoot, "link")))
		compare(t)
	})
	t.Run("hardlink", func(t *testing.T) {
		assert.NilError(t, os.Remove(filepath.Join(clientRoot, "link")))
		assert.NilError(t, os.Link(filepath.Join(clientRoot, "src/lib.rs"), filepath.Join(clientRoot, "linked")))
		compare(t)
	})
}

func TestSyncSnapshotSeedsCollectedParent(t *testing.T) {
	store := testutil.NewStore(t)
	clientRoot := writeTree(t, map[string]string{"file": "original"})
	client, err := fsutil.NewFS(clientRoot)
	assert.NilError(t, err)
	mirror := t.TempDir()
	seeds := &SnapshotSeeds{}
	makeLocal := func() *localFS {
		local, err := newLocalFS(NewMirrorSharedState(mirror), "", nil, nil, nil, "")
		assert.NilError(t, err)
		local.seeds, local.seedScope = seeds, "workspace"
		return local
	}
	first, owner := syncPublished(t, store, makeLocal(), client)
	oldID := first.SnapshotID()
	assert.NilError(t, first.Release(context.Background()))
	assert.NilError(t, store.Manager.RemoveLease(context.Background(), owner))
	store.GC(t)
	_, err = store.Manager.LeaseExistingSnapshot(context.Background(), oldID)
	assert.Assert(t, err != nil, "the parent must actually be collected")
	assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, "file"), []byte("new file contents"), 0o644))
	ref, owner := syncPublished(t, store, makeLocal(), client)
	defer ref.Release(context.Background())
	defer store.Manager.RemoveLease(context.Background(), owner)
	assertSyncedFile(t, ref, "file", "new file contents")
	seed, ok := seeds.get("workspace")
	assert.Assert(t, ok)
	assert.Equal(t, seed.depth, 0)
	assert.Equal(t, seedParentDepth(t, store.Manager, ref.SnapshotID()), 0)
}

func TestSyncSnapshotSeedsIgnoredAndScopedInputs(t *testing.T) {
	for _, scoped := range []bool{false, true} {
		t.Run(fmt.Sprintf("scoped=%t", scoped), func(t *testing.T) {
			prefix, copyPath := "", ""
			var includes []string
			if scoped {
				prefix, copyPath = "project/", "project"
				includes = []string{"!*", "project"}
			}
			clientRoot := writeTree(t, map[string]string{
				".gitignore":                "target/\nignored/\n!" + prefix + "ignored/keep.txt\n",
				prefix + "src/lib.rs":       "initial",
				prefix + "target/ignored":   "not imported",
				prefix + "ignored/keep.txt": "included through an ignored parent",
				prefix + "ignored/drop.txt": "not imported either",
				"projector/unrelated.txt":   "outside scoped import",
			})
			base, err := fsutil.NewFS(clientRoot)
			assert.NilError(t, err)
			marked, err := fsxutil.NewGitIgnoreMarkedFS(base, nil)
			assert.NilError(t, err)
			client, err := fsutil.NewFilterFS(marked, &fsutil.FilterOpt{IncludePatterns: includes})
			assert.NilError(t, err)
			store, fullStore := testutil.NewStore(t), testutil.NewStore(t)
			mirror, fullMirror := t.TempDir(), t.TempDir()
			seeds := &SnapshotSeeds{}
			for i := range 3 {
				assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, prefix, "src/lib.rs"), []byte(strings.Repeat("edit", i+1)), 0o644))
				local, err := newLocalFS(NewMirrorSharedState(mirror), "", includes, nil, nil, copyPath)
				assert.NilError(t, err)
				local.seeds, local.seedScope = seeds, "workspace"
				full, err := newLocalFS(NewMirrorSharedState(fullMirror), "", includes, nil, nil, copyPath)
				assert.NilError(t, err)
				candidate, owner := syncPublished(t, store, local, client)
				oracle, oracleOwner := syncPublished(t, fullStore, full, client)
				assert.Assert(t, is.DeepEqual(seedTestTree(t, testutil.Root(t, candidate)), seedTestTree(t, testutil.Root(t, oracle))))
				seedAssertDigest(t, candidate, oracle)
				seed, ok := seeds.get("workspace")
				assert.Assert(t, ok)
				assert.Equal(t, seed.depth, i)
				assertSyncedFile(t, candidate, "ignored/keep.txt", "included through an ignored parent")
				_, err = os.Stat(filepath.Join(testutil.Root(t, candidate), "target/ignored"))
				assert.Assert(t, os.IsNotExist(err))
				assert.NilError(t, candidate.Release(context.Background()))
				assert.NilError(t, store.Manager.RemoveLease(context.Background(), owner))
				assert.NilError(t, oracle.Release(context.Background()))
				assert.NilError(t, fullStore.Manager.RemoveLease(context.Background(), oracleOwner))
			}
		})
	}
}

func TestSyncSnapshotSeedsConcurrent(t *testing.T) {
	store := testutil.NewStore(t)
	clientRoot := writeTree(t, map[string]string{"file": "original", "keep": "keep"})
	client, err := fsutil.NewFS(clientRoot)
	assert.NilError(t, err)
	shared := NewMirrorSharedState(t.TempDir())
	seeds := &SnapshotSeeds{}
	makeLocal := func() *localFS {
		local, err := newLocalFS(shared, "", nil, nil, nil, "")
		assert.NilError(t, err)
		local.seeds, local.seedScope = seeds, "workspace"
		return local
	}
	first, owner := syncPublished(t, store, makeLocal(), client)
	t.Cleanup(func() {
		assert.NilError(t, first.Release(context.Background()))
		assert.NilError(t, store.Manager.RemoveLease(context.Background(), owner))
	})
	assert.NilError(t, os.WriteFile(filepath.Join(clientRoot, "file"), []byte("edited while both imports start"), 0o644))
	for _, name := range []string{"left", "right"} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			ref, owner := syncPublished(t, store, makeLocal(), client)
			defer ref.Release(context.Background())
			defer store.Manager.RemoveLease(context.Background(), owner)
			assertSyncedFile(t, ref, "file", "edited while both imports start")
			assertSyncedFile(t, ref, "keep", "keep")
			assertSyncedFile(t, first, "file", "original")
			assert.Assert(t, seedParentDepth(t, store.Manager, ref.SnapshotID()) <= 1)
		})
	}
}

func TestSnapshotSeedBounds(t *testing.T) {
	seeds := &SnapshotSeeds{}
	record := map[string]snapshotSeedRecord{"file": {}}
	for i := range maxSnapshotSeedScopes {
		seeds.put(strconv.Itoa(i), snapshotSeed{id: strconv.Itoa(i), records: record})
	}
	_, ok := seeds.get("0")
	assert.Assert(t, ok)
	seeds.put("new", snapshotSeed{id: "new", records: record})
	_, ok = seeds.get("0")
	assert.Assert(t, ok)
	_, ok = seeds.get("1")
	assert.Assert(t, !ok)
	large := make(map[string]snapshotSeedRecord, maxSnapshotSeedRecords/2+1)
	for i := range maxSnapshotSeedRecords/2 + 1 {
		large[strconv.Itoa(i)] = snapshotSeedRecord{}
	}
	seeds.put("large-first", snapshotSeed{id: "first", records: large})
	seeds.put("large-second", snapshotSeed{id: "second", records: large})
	assert.Assert(t, seeds.records <= maxSnapshotSeedRecords)
	_, ok = seeds.get("large-first")
	assert.Assert(t, !ok)
	_, ok = seeds.get("large-second")
	assert.Assert(t, ok)
}

func seedParentDepth(t *testing.T, manager bkcache.SnapshotManager, id string) int {
	t.Helper()
	depth := 0
	for {
		parent, err := manager.SnapshotParent(context.Background(), id)
		assert.NilError(t, err)
		if parent == "" {
			return depth
		}
		depth++
		assert.Assert(t, depth <= maxSnapshotSeedDepth)
		id = parent
	}
}

func seedAssertDigest(t *testing.T, candidate, oracle bkcache.ImmutableRef) {
	t.Helper()
	first, err := contenthash.Checksum(context.Background(), candidate, "/", contenthash.ChecksumOpts{})
	assert.NilError(t, err)
	second, err := contenthash.Checksum(context.Background(), oracle, "/", contenthash.ChecksumOpts{})
	assert.NilError(t, err)
	assert.Equal(t, first, second)
}

var errSeedCommit = errors.New("injected import commit failure")

type seedFailCommitManager struct{ bkcache.SnapshotManager }

func (m seedFailCommitManager) New(ctx context.Context, parent bkcache.ImmutableRef, opts ...bkcache.RefOption) (bkcache.MutableRef, error) {
	ref, err := m.SnapshotManager.New(ctx, parent, opts...)
	if err != nil {
		return nil, err
	}
	return seedFailCommitRef{MutableRef: ref, RefMetadata: ref.(bkcache.RefMetadata)}, nil
}

type seedFailCommitRef struct {
	bkcache.MutableRef
	bkcache.RefMetadata
}

func (r seedFailCommitRef) ID() string         { return r.MutableRef.ID() }
func (r seedFailCommitRef) SnapshotID() string { return r.MutableRef.SnapshotID() }
func (r seedFailCommitRef) Commit(context.Context) (bkcache.ImmutableRef, error) {
	return nil, errSeedCommit
}

type seedTestEntry struct {
	Mode     os.FileMode
	UID, GID uint32
	Content  string
	Hardlink string
	ModTime  int64
}

func seedTestTree(t *testing.T, root string) map[string]seedTestEntry {
	t.Helper()
	entries := make(map[string]seedTestEntry)
	inodes := make(map[[2]uint64]string)
	err := filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		stat := info.Sys().(*syscall.Stat_t)
		item := seedTestEntry{Mode: info.Mode(), UID: stat.Uid, GID: stat.Gid}
		if info.Mode().IsRegular() {
			contents, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			item.Content = string(contents)
			item.ModTime = info.ModTime().UnixNano()
			inode := [2]uint64{uint64(stat.Dev), stat.Ino}
			if first, ok := inodes[inode]; ok {
				item.Hardlink = first
			} else {
				inodes[inode] = rel
			}
		} else if info.Mode()&os.ModeSymlink != 0 {
			target, err := os.Readlink(path)
			if err != nil {
				return err
			}
			item.Content = target
		} else if !info.IsDir() {
			return fmt.Errorf("unexpected test entry %s: %s", path, info.Mode())
		}
		entries[rel] = item
		return nil
	})
	assert.NilError(t, err)
	return entries
}
