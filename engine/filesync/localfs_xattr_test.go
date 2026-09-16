//go:build linux

package filesync

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"path/filepath"
	"testing"

	"github.com/containerd/continuity/sysx"
	"github.com/dagger/dagger/internal/fsutil"
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/dagger/dagger/util/hashutil"
	digest "github.com/opencontainers/go-digest"
	"golang.org/x/sys/unix"
	"gotest.tools/v3/assert"
)

func TestLocalFSWalkSkipsXattrs(t *testing.T) {
	t.Parallel()

	root := writeTree(t, map[string]string{"dir/file": "contents"})
	wantDigest := digest.FromString("cached content hash")
	for _, path := range []string{"dir", "dir/file"} {
		setTestXattr(t, filepath.Join(root, path), hashXattrKey, []byte(wantDigest))
		setTestXattr(t, filepath.Join(root, path), "user.filesync-test", []byte("unused"))
	}
	local, err := newLocalFS(NewMirrorSharedState(root), "", nil, nil, nil, "")
	assert.NilError(t, err)

	var paths []string
	err = local.Walk(context.Background(), "/", func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		paths = append(paths, path)
		info, err := entry.Info()
		if err != nil {
			return err
		}
		stat := info.Sys().(*types.Stat)
		assert.Assert(t, stat.Xattrs == nil)

		want, err := fsutil.Stat(filepath.Join(root, path))
		assert.NilError(t, err)
		assert.Equal(t, string(want.Xattrs[hashXattrKey]), wantDigest.String())
		want.Path = path
		want.Xattrs = nil
		assert.DeepEqual(t, stat, want)

		if !entry.IsDir() {
			change, err := local.GetPreviousChange(context.Background(), path, stat)
			assert.NilError(t, err)
			defer change.release()
			assert.Equal(t, change.result().stat.Digest(), wantDigest)
		}
		return nil
	})
	assert.NilError(t, err)
	assert.DeepEqual(t, paths, []string{"dir", "dir/file"})
}

func TestLocalFSGetPreviousChangeRepairsMissingHashAfterWalk(t *testing.T) {
	t.Parallel()

	const contents = "contents to rehash"
	root := writeTree(t, map[string]string{"file": contents})
	fullPath := filepath.Join(root, "file")
	setTestXattr(t, fullPath, hashXattrKey, []byte(digest.FromString("old hash")))
	local, err := newLocalFS(NewMirrorSharedState(root), "", nil, nil, nil, "")
	assert.NilError(t, err)

	var stat *types.Stat
	err = local.Walk(context.Background(), "/", func(_ string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		stat = info.Sys().(*types.Stat)
		return nil
	})
	assert.NilError(t, err)
	assert.Assert(t, stat != nil)
	assert.Assert(t, stat.Xattrs == nil)

	// A hash present during the walk can disappear before the guarded lookup.
	// GetPreviousChange must still read and repair it, not reuse a walked value.
	assert.NilError(t, sysx.Removexattr(fullPath, hashXattrKey))
	h := newHashFromStat(stat)
	_, err = io.WriteString(h, contents)
	assert.NilError(t, err)
	want := digest.NewDigest(hashutil.XXH3, h)
	change, err := local.GetPreviousChange(context.Background(), "file", stat)
	assert.NilError(t, err)
	defer change.release()
	assert.Equal(t, change.result().kind, ChangeKindNone)
	assert.Equal(t, change.result().stat.Digest(), want)
	repaired, err := sysx.Getxattr(fullPath, hashXattrKey)
	assert.NilError(t, err)
	assert.Equal(t, string(repaired), want.String())
}

func setTestXattr(t *testing.T, path, key string, value []byte) {
	t.Helper()
	err := sysx.Setxattr(path, key, value, 0)
	if errors.Is(err, unix.ENOTSUP) {
		t.Skip("filesystem does not support xattrs")
	}
	assert.NilError(t, err)
}
