//go:build linux

package fsutil

import (
	"context"
	"errors"
	gofs "io/fs"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/containerd/continuity/sysx"
	"github.com/dagger/dagger/internal/fsutil/types"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestFSWithSkipXattrs(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	require.NoError(t, os.Mkdir(filepath.Join(root, "dir"), 0o750))
	file := filepath.Join(root, "dir", "file")
	require.NoError(t, os.WriteFile(file, []byte("contents"), 0o640))
	mtime := time.Unix(1234567890, 123456789)
	require.NoError(t, os.Chtimes(file, mtime, mtime))
	require.NoError(t, os.Link(file, filepath.Join(root, "hardlink")))
	require.NoError(t, os.Symlink("dir/file", filepath.Join(root, "symlink")))
	require.NoError(t, os.Symlink("missing", filepath.Join(root, "dangling")))

	const xattr = "user.fsutil-test"
	for _, path := range []string{file, filepath.Join(root, "dir")} {
		err := sysx.Setxattr(path, xattr, []byte("value"), 0)
		if errors.Is(err, unix.ENOTSUP) {
			t.Skip("filesystem does not support xattrs")
		}
		require.NoError(t, err)
		stat, err := Stat(path)
		require.NoError(t, err)
		require.Equal(t, []byte("value"), stat.Xattrs[xattr], "Stat must still read xattrs")
	}

	for _, tc := range []struct {
		name   string
		filter *FilterOpt
	}{
		{name: "unfiltered"},
		{name: "filtered hardlink source", filter: &FilterOpt{ExcludePatterns: []string{"dir/file"}}},
		{name: "follow symlink", filter: &FilterOpt{FollowPaths: []string{"symlink"}}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			walk := func(opts ...FSOpt) map[string]*types.Stat {
				t.Helper()
				fs, err := NewFS(root, opts...)
				require.NoError(t, err)
				fs, err = NewFilterFS(fs, tc.filter)
				require.NoError(t, err)
				fs = WithHardlinkReset(fs)
				stats := map[string]*types.Stat{}
				err = fs.Walk(context.Background(), "/", func(path string, entry gofs.DirEntry, err error) error {
					if err != nil {
						return err
					}
					info, err := entry.Info()
					if err != nil {
						return err
					}
					stats[path] = info.Sys().(*types.Stat)
					return nil
				})
				require.NoError(t, err)
				return stats
			}

			want := walk()
			got := walk(WithSkipXattrs())
			require.Equal(t, []byte("value"), want["dir"].Xattrs[xattr])
			for path, stat := range want {
				require.Contains(t, got, path)
				require.Nil(t, got[path].Xattrs)
				stat.Xattrs = nil
			}
			require.Equal(t, want, got, "only xattrs should differ")
			require.Equal(t, "dir/file", got["symlink"].Linkname)
			if tc.filter == nil {
				require.Equal(t, "dir/file", got["hardlink"].Linkname)
				require.Equal(t, "missing", got["dangling"].Linkname)
				require.Equal(t, mtime.UnixNano(), got["dir/file"].ModTime)
			}
			if tc.name == "filtered hardlink source" {
				require.NotContains(t, got, "dir/file")
				require.Empty(t, got["hardlink"].Linkname)
			}
		})
	}
}
