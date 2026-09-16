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
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/layercopy"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestFileCacheResultFirstAfterSkippedXattrHashRepair(t *testing.T) {
	t.Parallel()

	for _, tc := range []struct {
		name       string
		cachedBlob bool
	}{
		{name: "blob absent"},
		{name: "blob present", cachedBlob: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			ctx := context.Background()
			const contents = "contents whose mirror hash needs repair"
			const unusedXattr = "user.filesync-combined-test"
			root := writeTree(t, map[string]string{"files/file": contents})
			filesRoot := filepath.Join(root, "files")
			blobRoot := filepath.Join(root, "blobs")
			require.NoError(t, os.Mkdir(blobRoot, 0o700))
			source := filepath.Join(filesRoot, "file")
			mtime := time.Unix(1_700_000_000, 123_456_789)
			require.NoError(t, os.Chmod(source, 0o640))
			require.NoError(t, os.Chtimes(source, mtime, mtime))
			want := fileCacheTestStat(t, source)
			wantKey := fileCacheKey(want)
			cachePath := fileCachePath(blobRoot, wantKey)
			setTestXattr(t, source, hashXattrKey, []byte(want.Digest().String()))
			setTestXattr(t, source, unusedXattr, []byte("mirror only"))
			local, err := newLocalFS(NewMirrorSharedStateWithFileCache(filesRoot, blobRoot), "", nil, nil, nil, "")
			require.NoError(t, err)

			walk := func() *types.Stat {
				t.Helper()
				var stat *types.Stat
				var paths []string
				err := local.Walk(ctx, "/", func(path string, entry fs.DirEntry, err error) error {
					if err != nil {
						return err
					}
					info, err := entry.Info()
					if err != nil {
						return err
					}
					stat = info.Sys().(*types.Stat)
					require.Nil(t, stat.Xattrs, "the mirror walk must skip all xattrs")
					paths = append(paths, path)
					return nil
				})
				require.NoError(t, err)
				require.Equal(t, []string{"file"}, paths, "the sibling blob cache must not enter the mirror walk")
				return stat
			}

			var previous os.FileInfo
			if tc.cachedBlob {
				func() {
					seedChange, err := local.GetPreviousChange(ctx, "file", walk())
					require.NoError(t, err)
					// Release before the next lookup so the in-memory change cache
					// cannot hide the missing on-disk hash in the repair phase.
					defer seedChange.release()
					seed := local.newFileCacheCopy(ctx, []CachedChange{seedChange})
					copier, _ := fileCacheResultFirstCopier(t)
					copyErr := copier.CopyToEmpty(ctx, layercopy.Mount{Root: filesRoot}, "/", fileCacheResultFirstOptions(seed.lookup), seed.materialize)
					closeErr := copier.Close()
					require.NoError(t, copyErr)
					require.NoError(t, closeErr)
					require.NoError(t, seed.publish(ctx))
				}()
				previous = fileCacheTestInfo(t, cachePath)
			} else {
				assertFileCacheResultFirstEmpty(t, blobRoot)
			}

			stat := walk()
			// Simulate a hash disappearing after discovery. The actual guarded
			// lookup, not the walked stat or a test-generated change, feeds CAS.
			require.NoError(t, sysx.Removexattr(source, hashXattrKey))
			change, err := local.GetPreviousChange(ctx, "file", stat)
			require.NoError(t, err)
			defer change.release()
			require.Equal(t, ChangeKindNone, change.result().kind)
			require.Equal(t, want.Digest(), change.result().stat.Digest())
			require.Equal(t, wantKey, fileCacheKey(change.result().stat), "repair must preserve the metadata-compatible blob key")
			require.Nil(t, change.result().stat.Xattrs)
			repaired, err := sysx.Getxattr(source, hashXattrKey)
			require.NoError(t, err)
			require.Equal(t, want.Digest().String(), string(repaired))

			cache := local.newFileCacheCopy(ctx, []CachedChange{change})
			copier, result := fileCacheResultFirstCopier(t)
			lookups, materialized := 0, 0
			opts := fileCacheResultFirstOptions(func(path string, info os.FileInfo) (string, error) {
				lookups++
				require.Equal(t, source, path)
				cached, err := cache.lookup(path, info)
				if err == nil {
					if tc.cachedBlob {
						require.Equal(t, cachePath, cached)
					} else {
						require.Empty(t, cached)
					}
				}
				return cached, err
			})
			copyErr := copier.CopyToEmpty(ctx, layercopy.Mount{Root: filesRoot}, "/", opts, func(source, destination string, info os.FileInfo) (bool, error) {
				handled, err := cache.materialize(source, destination, info)
				if handled && err == nil {
					materialized++
				}
				return handled, err
			})
			closeErr := copier.Close()
			require.NoError(t, copyErr)
			require.NoError(t, closeErr)
			require.Equal(t, 1, lookups)
			resultPath := filepath.Join(result, "file")
			resultInfo := fileCacheTestInfo(t, resultPath)
			if tc.cachedBlob {
				require.Zero(t, materialized, "the repaired digest must reuse the existing blob")
				require.True(t, os.SameFile(previous, resultInfo))
			} else {
				require.Equal(t, 1, materialized, "a cache miss must verify a new result inode")
				assertFileCacheResultFirstEmpty(t, blobRoot)
			}
			require.NoError(t, cache.publish(ctx))
			require.True(t, os.SameFile(resultInfo, fileCacheTestInfo(t, cachePath)))

			for _, path := range []string{resultPath, cachePath} {
				assertFileCacheContents(t, path, contents)
				require.False(t, os.SameFile(fileCacheTestInfo(t, source), fileCacheTestInfo(t, path)))
				actual, err := fsutil.Stat(path)
				require.NoError(t, err)
				require.Empty(t, actual.Xattrs, "result and blob must not retain mirror xattrs")
				expected := *want.Stat
				expected.Path = actual.Path
				expected.Xattrs = nil
				require.Equal(t, &expected, actual, "contents-independent metadata must survive hash repair and copying")
				for _, key := range []string{hashXattrKey, unusedXattr} {
					_, err := sysx.Getxattr(path, key)
					require.ErrorIs(t, err, unix.ENODATA)
				}
			}
			assertFileCacheContents(t, source, contents)
			unused, err := sysx.Getxattr(source, unusedXattr)
			require.NoError(t, err)
			require.Equal(t, "mirror only", string(unused))
		})
	}
}
