//go:build linux

package filesync

import (
	"context"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/containerd/continuity/sysx"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/util/hashutil"
	"github.com/dagger/dagger/util/layercopy"
	digest "github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestCachedFileRejectsChangedSource(t *testing.T) {
	t.Parallel()

	for name, changed := range map[string]string{
		"same size":      "after!",
		"different size": "longer contents",
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			source := filepath.Join(writeTree(t, map[string]string{"file": "before"}), "file")
			stat := fileCacheTestStat(t, source)
			require.NoError(t, os.WriteFile(source, []byte(changed), 0o644))

			cacheRoot := t.TempDir()
			path, err := cachedFile(context.Background(), cacheRoot, digest.FromString("object"), source, stat)
			require.ErrorContains(t, err, "source changed while copying")
			require.Empty(t, path)
			require.NoError(t, filepath.WalkDir(cacheRoot, func(_ string, entry fs.DirEntry, err error) error {
				require.NoError(t, err)
				require.True(t, entry.IsDir(), "failed ingestion must leave no published or temporary files")
				return nil
			}))
		})
	}
}

func TestCachedFileStripsMirrorXattr(t *testing.T) {
	t.Parallel()

	source := filepath.Join(writeTree(t, map[string]string{"file": "contents"}), "file")
	require.NoError(t, sysx.Setxattr(source, hashXattrKey, []byte("private mirror metadata"), 0))
	stat := fileCacheTestStat(t, source)
	path, err := cachedFile(context.Background(), t.TempDir(), digest.FromString("object"), source, stat)
	require.NoError(t, err)

	_, err = sysx.Getxattr(path, hashXattrKey)
	require.ErrorIs(t, err, unix.ENODATA)
	value, err := sysx.Getxattr(source, hashXattrKey)
	require.NoError(t, err)
	require.Equal(t, "private mirror metadata", string(value))
	assertFileCacheContents(t, path, "contents")
	require.False(t, os.SameFile(fileCacheTestInfo(t, source), fileCacheTestInfo(t, path)))
	require.Equal(t, stat.Mode(), fileCacheTestInfo(t, path).Mode())
	require.Equal(t, stat.ModTime(), fileCacheTestInfo(t, path).ModTime())
}

func TestImmutableFileSourceMetadataIdentity(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"file": "contents"})
	local := fileCacheTestLocal(t, root)
	source := filepath.Join(root, "file")
	firstTime := time.Unix(1_700_000_000, 123_456_789)
	require.NoError(t, os.Chtimes(source, firstTime, firstTime))
	firstStat := fileCacheTestStat(t, source)
	first := fileCacheTestResolve(t, local, "file")

	secondTime := firstTime.Add(time.Second)
	require.NoError(t, os.Chtimes(source, secondTime, secondTime))
	secondStat := fileCacheTestStat(t, source)
	second := fileCacheTestResolve(t, local, "file")
	require.Equal(t, firstStat.Digest(), secondStat.Digest(), "semantic hashes omit mtime")
	require.NotEqual(t, first, second, "inodes with different mtimes cannot be shared")
	require.Equal(t, firstTime, fileCacheTestInfo(t, first).ModTime())
	require.Equal(t, secondTime, fileCacheTestInfo(t, second).ModTime())

	require.NoError(t, os.Chmod(source, 0o640))
	third := fileCacheTestResolve(t, local, "file")
	require.NotEqual(t, second, third)
	require.Equal(t, os.FileMode(0o644), fileCacheTestInfo(t, second).Mode())
	require.Equal(t, os.FileMode(0o640), fileCacheTestInfo(t, third).Mode())
}

func TestFileCacheFlatCopiesReuseImmutableFiles(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"file": "before"})
	local := fileCacheTestLocal(t, root)
	cachePath := fileCacheTestResolve(t, local, "file")
	first := fileCacheTestCopy(t, local, "file")
	second := fileCacheTestCopy(t, local, "file")
	firstPath := filepath.Join(first, "file")
	secondPath := filepath.Join(second, "file")
	require.True(t, os.SameFile(fileCacheTestInfo(t, cachePath), fileCacheTestInfo(t, firstPath)))
	require.True(t, os.SameFile(fileCacheTestInfo(t, firstPath), fileCacheTestInfo(t, secondPath)))
	require.False(t, os.SameFile(fileCacheTestInfo(t, filepath.Join(root, "file")), fileCacheTestInfo(t, firstPath)))

	// Even an in-place mirror write must not mutate the sealed cache inode.
	require.NoError(t, os.WriteFile(filepath.Join(root, "file"), []byte("after!"), 0o644))
	third := fileCacheTestCopy(t, local, "file")
	assertFileCacheContents(t, filepath.Join(third, "file"), "after!")
	require.False(t, os.SameFile(fileCacheTestInfo(t, firstPath), fileCacheTestInfo(t, filepath.Join(third, "file"))))

	// Cache ownership is not needed once a flat result holds its own link.
	require.NoError(t, os.Remove(cachePath))
	assertFileCacheContents(t, firstPath, "before")
	assertFileCacheContents(t, secondPath, "before")
}

func TestFileCacheDoesNotAliasIndependentEqualFiles(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"a": "equal", "b": "equal"})
	mtime := time.Unix(1_700_000_000, 0)
	for _, name := range []string{"a", "b"} {
		require.NoError(t, os.Chtimes(filepath.Join(root, name), mtime, mtime))
	}
	local := fileCacheTestLocal(t, root)
	result := fileCacheTestCopy(t, local, "a", "b")
	a := filepath.Join(result, "a")
	b := filepath.Join(result, "b")
	require.False(t, os.SameFile(fileCacheTestInfo(t, a), fileCacheTestInfo(t, b)))
	// The independent, copied inode remains independent even when mutated.
	require.NoError(t, os.WriteFile(b, []byte("other"), 0o644))
	assertFileCacheContents(t, a, "equal")
}

func TestFileCachePreservesSourceHardlinkGroup(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"a": "linked"})
	a := filepath.Join(root, "a")
	b := filepath.Join(root, "b")
	require.NoError(t, os.Link(a, b))
	mtime := time.Unix(1_700_000_000, 123_456_789)
	require.NoError(t, os.Chtimes(a, mtime, mtime))
	// An unnecessary chown through the second alias clears this mode bit.
	require.NoError(t, os.Chmod(a, 0o755|os.ModeSetuid))
	local := fileCacheTestLocal(t, root)
	cachePath := fileCacheTestResolve(t, local, "a")
	cacheBefore := fileCacheTestInfo(t, cachePath)
	result := fileCacheTestCopy(t, local, "a", "b")
	resultA := fileCacheTestInfo(t, filepath.Join(result, "a"))
	resultB := fileCacheTestInfo(t, filepath.Join(result, "b"))
	require.True(t, os.SameFile(resultA, resultB))
	require.True(t, os.SameFile(cacheBefore, resultA))
	require.Equal(t, cacheBefore.Mode(), fileCacheTestInfo(t, cachePath).Mode())
	require.Equal(t, cacheBefore.ModTime(), fileCacheTestInfo(t, cachePath).ModTime())
	require.Equal(t, os.FileMode(0o755)|os.ModeSetuid, fileCacheTestInfo(t, a).Mode())
	require.Equal(t, mtime, fileCacheTestInfo(t, a).ModTime())
}

func fileCacheTestStat(t *testing.T, path string) *HashedStatInfo {
	t.Helper()
	stat, err := fsutil.Stat(path)
	require.NoError(t, err)
	contents, err := os.ReadFile(path)
	require.NoError(t, err)
	h := newHashFromStat(stat)
	_, err = h.Write(contents)
	require.NoError(t, err)
	return &HashedStatInfo{
		StatInfo: StatInfo{stat},
		dgst:     digest.NewDigest(hashutil.XXH3, h),
	}
}

func fileCacheTestLocal(t *testing.T, root string) *localFS {
	t.Helper()
	local, err := newLocalFS(NewMirrorSharedStateWithFileCache(root, t.TempDir()), "", nil, nil, nil, "")
	require.NoError(t, err)
	return local
}

func fileCacheTestChanges(t *testing.T, local *localFS, names ...string) []CachedChange {
	t.Helper()
	changes := make([]CachedChange, 0, len(names))
	for _, name := range names {
		changes = append(changes, &cachedChange{
			callKey: name,
			val: &ChangeWithStat{
				kind: ChangeKindNone,
				stat: fileCacheTestStat(t, filepath.Join(local.rootPath, name)),
			},
		})
	}
	return changes
}

func fileCacheTestResolve(t *testing.T, local *localFS, name string) string {
	t.Helper()
	source := filepath.Join(local.rootPath, name)
	resolve := local.immutableFileSource(context.Background(), fileCacheTestChanges(t, local, name))
	path, err := resolve(source, fileCacheTestInfo(t, source))
	require.NoError(t, err)
	require.NotEmpty(t, path)
	return path
}

func fileCacheTestCopy(t *testing.T, local *localFS, names ...string) string {
	t.Helper()
	root := t.TempDir()
	copier, err := layercopy.NewCopier(layercopy.Mount{Root: root})
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, copier.Close()) })
	require.NoError(t, copier.Copy(context.Background(), layercopy.Mount{Root: local.rootPath}, "/", "/", layercopy.CopyOptions{
		CopyDirContents:        true,
		DisableSourceHardlinks: true,
		DisableXAttrs:          true,
		ImmutableFileSource:    local.immutableFileSource(context.Background(), fileCacheTestChanges(t, local, names...)),
	}))
	return root
}

func fileCacheTestInfo(t *testing.T, path string) os.FileInfo {
	t.Helper()
	info, err := os.Stat(path)
	require.NoError(t, err)
	return info
}

func assertFileCacheContents(t *testing.T, path, want string) {
	t.Helper()
	contents, err := os.ReadFile(path)
	require.NoError(t, err)
	require.Equal(t, want, string(contents))
}
