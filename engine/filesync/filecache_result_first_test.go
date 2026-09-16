//go:build linux

package filesync

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/containerd/continuity/sysx"
	"github.com/dagger/dagger/util/layercopy"
	digest "github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestFileCacheResultFirstPublishesFinalizedResultInode(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"file": "contents"})
	source := filepath.Join(root, "file")
	mtime := time.Unix(1_700_000_000, 123_456_789)
	require.NoError(t, os.Chmod(source, 0o640))
	require.NoError(t, os.Chtimes(source, mtime, mtime))
	local := fileCacheTestLocal(t, root)
	cachePath := fileCacheResultFirstPath(t, local, "file")
	ctx := context.Background()
	cache := local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "file"))
	copier, result := fileCacheResultFirstCopier(t)
	resultPath := filepath.Join(result, "file")

	require.NoError(t, copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", fileCacheResultFirstOptions(cache.lookup), cache.materialize))
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
	resultInfo := fileCacheTestInfo(t, resultPath)
	require.False(t, os.SameFile(fileCacheTestInfo(t, source), resultInfo), "the mutable mirror must not share the result inode")
	require.Equal(t, os.FileMode(0o640), resultInfo.Mode())
	require.Equal(t, mtime, resultInfo.ModTime())
	assertFileCacheContents(t, resultPath, "contents")

	require.NoError(t, copier.Close())
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
	require.NoError(t, cache.publish(ctx))
	cacheInfo := fileCacheTestInfo(t, cachePath)
	require.True(t, os.SameFile(resultInfo, cacheInfo), "cold publication must retain the finalized result inode, not copy it again")
	require.Equal(t, resultInfo.Mode(), cacheInfo.Mode())
	require.Equal(t, resultInfo.ModTime(), cacheInfo.ModTime())
	assertFileCacheContents(t, cachePath, "contents")

	require.NoError(t, os.WriteFile(source, []byte("changed!"), 0o640))
	assertFileCacheContents(t, resultPath, "contents")
	assertFileCacheContents(t, cachePath, "contents")
	require.NoError(t, os.Remove(cachePath))
	assertFileCacheContents(t, resultPath, "contents")
}

func TestFileCacheResultFirstRejectsChangedSource(t *testing.T) {
	t.Parallel()

	for name, changed := range map[string]string{
		"same size":      "after!",
		"different size": "longer contents",
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			root := writeTree(t, map[string]string{"file": "before"})
			local := fileCacheTestLocal(t, root)
			ctx := context.Background()
			cache := local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "file"))
			require.NoError(t, os.WriteFile(filepath.Join(root, "file"), []byte(changed), 0o644))
			copier, _ := fileCacheResultFirstCopier(t)

			err := copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", fileCacheResultFirstOptions(cache.lookup), cache.materialize)
			require.ErrorContains(t, err, "source changed while copying")
			require.NoError(t, copier.Close())
			assertFileCacheResultFirstEmpty(t, local.blobRoot)
		})
	}
}

func TestFileCacheResultFirstDoesNotPublishFailedCopy(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"a": "completed", "b": "later"})
	local := fileCacheTestLocal(t, root)
	ctx := context.Background()
	cache := local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "a", "b"))
	copier, result := fileCacheResultFirstCopier(t)
	wantErr := errors.New("later file failed")
	materialized := 0
	err := copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", fileCacheResultFirstOptions(cache.lookup), func(source, destination string, info os.FileInfo) (bool, error) {
		if filepath.Base(source) == "b" {
			return false, wantErr
		}
		handled, err := cache.materialize(source, destination, info)
		if handled && err == nil {
			materialized++
		}
		assertFileCacheResultFirstEmpty(t, local.blobRoot)
		return handled, err
	})
	require.ErrorIs(t, err, wantErr)
	require.Equal(t, 1, materialized, "a completed candidate must precede the failing file")
	assertFileCacheContents(t, filepath.Join(result, "a"), "completed")
	require.NoError(t, copier.Close())
	// The caller only publishes after the entire copy and Close succeed.
	// An earlier candidate must not have been published by either operation.
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
}

func TestFileCacheResultFirstPreservesFinalizedHardlinkMetadata(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"a": "linked"})
	sourceA := filepath.Join(root, "a")
	require.NoError(t, os.Link(sourceA, filepath.Join(root, "b")))
	mtime := time.Unix(1_700_000_000, 123_456_789)
	mode := os.FileMode(0o755) | os.ModeSetuid
	require.NoError(t, os.Chtimes(sourceA, mtime, mtime))
	require.NoError(t, os.Chmod(sourceA, mode))
	local := fileCacheTestLocal(t, root)
	cachePath := fileCacheResultFirstPath(t, local, "a")
	ctx := context.Background()
	cache := local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "a", "b"))
	copier, result := fileCacheResultFirstCopier(t)
	profile := &layercopy.CopyProfile{}
	opts := fileCacheResultFirstOptions(cache.lookup)
	opts.Profile = profile
	materialized := 0
	metadataCalls := map[string]int64{}
	require.NoError(t, copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", opts, func(source, destination string, info os.FileInfo) (bool, error) {
		handled, err := cache.materialize(source, destination, info)
		if handled && err == nil {
			materialized++
			require.Equal(t, mode, fileCacheTestInfo(t, destination).Mode())
			require.Equal(t, mtime, fileCacheTestInfo(t, destination).ModTime())
			for _, operation := range []string{"metadata.chown", "metadata.chmod", "metadata.utimes"} {
				metadataCalls[operation] = profile.Operations[operation].Calls
			}
		}
		return handled, err
	}))
	require.Equal(t, 1, materialized)
	for operation, calls := range metadataCalls {
		require.Equal(t, calls, profile.Operations[operation].Calls, "finalized aliases must not reapply %s", operation)
	}
	resultA := fileCacheTestInfo(t, filepath.Join(result, "a"))
	resultB := fileCacheTestInfo(t, filepath.Join(result, "b"))
	require.True(t, os.SameFile(resultA, resultB))
	require.False(t, os.SameFile(fileCacheTestInfo(t, sourceA), resultA))
	require.Equal(t, mode, resultA.Mode())
	require.Equal(t, mtime, resultA.ModTime())
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
	require.NoError(t, copier.Close())
	require.NoError(t, cache.publish(ctx))
	cacheInfo := fileCacheTestInfo(t, cachePath)
	require.True(t, os.SameFile(resultA, cacheInfo))
	require.Equal(t, mode, cacheInfo.Mode())
	require.Equal(t, mtime, cacheInfo.ModTime())
	require.Equal(t, mode, fileCacheTestInfo(t, sourceA).Mode())
	require.Equal(t, mtime, fileCacheTestInfo(t, sourceA).ModTime())
}

func TestFileCacheResultFirstKeepsEqualFilesIndependent(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"a": "equal", "b": "equal"})
	mtime := time.Unix(1_700_000_000, 0)
	for _, name := range []string{"a", "b"} {
		require.NoError(t, os.Chtimes(filepath.Join(root, name), mtime, mtime))
	}
	local := fileCacheTestLocal(t, root)
	cachePath := fileCacheResultFirstPath(t, local, "a")
	require.Equal(t, cachePath, fileCacheResultFirstPath(t, local, "b"))
	ctx := context.Background()
	cache := local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "a", "b"))
	copier, result := fileCacheResultFirstCopier(t)
	require.NoError(t, copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", fileCacheResultFirstOptions(cache.lookup), cache.materialize))
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
	require.NoError(t, copier.Close())
	require.NoError(t, cache.publish(ctx))

	a := filepath.Join(result, "a")
	b := filepath.Join(result, "b")
	aInfo := fileCacheTestInfo(t, a)
	bInfo := fileCacheTestInfo(t, b)
	cacheInfo := fileCacheTestInfo(t, cachePath)
	require.False(t, os.SameFile(aInfo, bInfo))
	aIsCached := os.SameFile(aInfo, cacheInfo)
	bIsCached := os.SameFile(bInfo, cacheInfo)
	require.NotEqual(t, aIsCached, bIsCached, "only one independent file may own this copy's cache key")
	cachedResult, independentResult := a, b
	if bIsCached {
		cachedResult, independentResult = b, a
	}
	require.NoError(t, os.WriteFile(independentResult, []byte("other"), 0o644))
	assertFileCacheContents(t, cachedResult, "equal")
	assertFileCacheContents(t, cachePath, "equal")
	assertFileCacheContents(t, filepath.Join(root, "a"), "equal")
	assertFileCacheContents(t, filepath.Join(root, "b"), "equal")
}

func TestFileCacheResultFirstStripsMirrorXattr(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"file": "contents"})
	source := filepath.Join(root, "file")
	require.NoError(t, sysx.Setxattr(source, hashXattrKey, []byte("private mirror metadata"), 0))
	local := fileCacheTestLocal(t, root)
	cachePath := fileCacheResultFirstPath(t, local, "file")
	ctx := context.Background()
	cache := local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "file"))
	copier, result := fileCacheResultFirstCopier(t)
	require.NoError(t, copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", fileCacheResultFirstOptions(cache.lookup), cache.materialize))
	resultPath := filepath.Join(result, "file")
	_, err := sysx.Getxattr(resultPath, hashXattrKey)
	require.ErrorIs(t, err, unix.ENODATA)
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
	require.NoError(t, copier.Close())
	require.NoError(t, cache.publish(ctx))
	_, err = sysx.Getxattr(cachePath, hashXattrKey)
	require.ErrorIs(t, err, unix.ENODATA)
	value, err := sysx.Getxattr(source, hashXattrKey)
	require.NoError(t, err)
	require.Equal(t, "private mirror metadata", string(value))
	require.True(t, os.SameFile(fileCacheTestInfo(t, resultPath), fileCacheTestInfo(t, cachePath)))
	assertFileCacheContents(t, cachePath, "contents")
}

func TestFileCacheResultFirstConcurrentPublishers(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"file": "contents"})
	require.NoError(t, os.Chmod(filepath.Join(root, "file"), 0o640))
	local := fileCacheTestLocal(t, root)
	ctx := context.Background()
	var caches [2]*fileCacheCopy
	var results [2]string
	var before [2]os.FileInfo
	for i := range caches {
		caches[i] = local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "file"))
		copier, result := fileCacheResultFirstCopier(t)
		require.NoError(t, copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", fileCacheResultFirstOptions(caches[i].lookup), caches[i].materialize))
		require.NoError(t, copier.Close())
		results[i] = filepath.Join(result, "file")
		before[i] = fileCacheTestInfo(t, results[i])
	}
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
	require.False(t, os.SameFile(before[0], before[1]))

	errs := make(chan error, len(caches))
	for _, cache := range caches {
		go func() { errs <- cache.publish(ctx) }()
	}
	for range caches {
		require.NoError(t, <-errs)
	}
	cachePath := fileCacheResultFirstPath(t, local, "file")
	cacheInfo := fileCacheTestInfo(t, cachePath)
	winners := 0
	for i, path := range results {
		after := fileCacheTestInfo(t, path)
		require.True(t, os.SameFile(before[i], after))
		require.Equal(t, os.FileMode(0o640), after.Mode())
		require.Equal(t, before[i].ModTime(), after.ModTime())
		assertFileCacheContents(t, path, "contents")
		if os.SameFile(after, cacheInfo) {
			winners++
		}
	}
	require.Equal(t, 1, winners, "no-replace publication must retain exactly one result inode")
	require.Equal(t, os.FileMode(0o640), cacheInfo.Mode())
	assertFileCacheContents(t, cachePath, "contents")
}

func TestFileCacheResultFirstMaterializesDisappearedCacheHit(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"file": "contents"})
	local := fileCacheTestLocal(t, root)
	cachePath := fileCacheTestResolve(t, local, "file")
	previous := fileCacheTestInfo(t, cachePath)
	ctx := context.Background()
	cache := local.newFileCacheCopy(ctx, fileCacheTestChanges(t, local, "file"))
	copier, result := fileCacheResultFirstCopier(t)
	removed := false
	opts := fileCacheResultFirstOptions(func(source string, info os.FileInfo) (string, error) {
		path, err := cache.lookup(source, info)
		require.NoError(t, err)
		require.Equal(t, cachePath, path)
		require.NoError(t, os.Remove(path))
		removed = true
		return path, nil
	})
	materialized := 0
	require.NoError(t, copier.CopyToEmpty(ctx, layercopy.Mount{Root: root}, "/", opts, func(source, destination string, info os.FileInfo) (bool, error) {
		handled, err := cache.materialize(source, destination, info)
		if handled && err == nil {
			materialized++
		}
		return handled, err
	}))
	require.True(t, removed)
	require.Equal(t, 1, materialized, "a disappeared hit must use verified materialization")
	resultPath := filepath.Join(result, "file")
	resultInfo := fileCacheTestInfo(t, resultPath)
	require.False(t, os.SameFile(previous, resultInfo))
	require.Equal(t, previous.Mode(), resultInfo.Mode())
	require.Equal(t, previous.ModTime(), resultInfo.ModTime())
	assertFileCacheContents(t, resultPath, "contents")
	assertFileCacheResultFirstEmpty(t, local.blobRoot)
	require.NoError(t, copier.Close())
	require.NoError(t, cache.publish(ctx))
	require.True(t, os.SameFile(resultInfo, fileCacheTestInfo(t, cachePath)))
	assertFileCacheContents(t, cachePath, "contents")
}

func fileCacheResultFirstOptions(lookup func(string, os.FileInfo) (string, error)) layercopy.CopyOptions {
	return layercopy.CopyOptions{
		CopyDirContents:        true,
		DisableSourceHardlinks: true,
		DisableXAttrs:          true,
		ImmutableFileSource:    lookup,
	}
}

func fileCacheResultFirstCopier(t *testing.T) (*layercopy.Copier, string) {
	t.Helper()
	root := t.TempDir()
	copier, err := layercopy.NewCopier(layercopy.Mount{Root: root})
	require.NoError(t, err)
	return copier, root
}

func fileCacheResultFirstPath(t *testing.T, local *localFS, name string) string {
	t.Helper()
	stat := fileCacheTestStat(t, filepath.Join(local.rootPath, name))
	key := digest.FromString(fmt.Sprintf("%s:%d:%d", stat.Digest(), stat.ModTime().UnixNano(), stat.Size())).Encoded()
	return filepath.Join(local.blobRoot, key[:2], key[2:])
}

func assertFileCacheResultFirstEmpty(t *testing.T, root string) {
	t.Helper()
	require.NoError(t, filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		require.NoError(t, err)
		require.True(t, entry.IsDir(), "unpublished copies must leave no cache files: %s", path)
		return nil
	}))
}
