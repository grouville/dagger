//go:build linux

package layercopy

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/containerd/continuity/sysx"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestCopyFileMixedModesPreserveImmutableDonors(t *testing.T) {
	t.Parallel()

	for _, cached := range []bool{false, true} {
		name := "direct source"
		if cached {
			name = "immutable callback"
		}
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			root := t.TempDir()
			source := filepath.Join(root, "source")
			donor := source
			require.NoError(t, os.WriteFile(source, []byte("contents"), 0o644))
			opts := CopyOptions{}
			if cached {
				donor = filepath.Join(root, "cached")
				require.NoError(t, os.WriteFile(donor, []byte("contents"), 0o644))
				mtime := copyMetadataTestInfo(t, source).ModTime()
				require.NoError(t, os.Chtimes(donor, mtime, mtime))
				opts.ImmutableFileSource = func(string, os.FileInfo) (string, error) {
					return donor, nil
				}
			}

			dest := t.TempDir()
			copier, err := NewCopier(Mount{Root: dest})
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, copier.Close()) })
			src := Mount{Root: root}
			require.NoError(t, copier.CopyFile(context.Background(), src, "/source", "/first", opts))
			privateMode := os.FileMode(0o600)
			privateOpts := opts
			privateOpts.Mode = &privateMode
			require.NoError(t, copier.CopyFile(context.Background(), src, "/source", "/private", privateOpts))
			require.NoError(t, copier.CopyFile(context.Background(), src, "/source", "/last", opts))

			first := copyMetadataTestInfo(t, filepath.Join(dest, "first"))
			private := copyMetadataTestInfo(t, filepath.Join(dest, "private"))
			last := copyMetadataTestInfo(t, filepath.Join(dest, "last"))
			require.Equal(t, os.FileMode(0o644), first.Mode())
			require.Equal(t, os.FileMode(0o600), private.Mode())
			require.Equal(t, os.FileMode(0o644), last.Mode())
			require.Equal(t, os.FileMode(0o644), copyMetadataTestInfo(t, source).Mode())
			require.Equal(t, os.FileMode(0o644), copyMetadataTestInfo(t, donor).Mode())
			require.True(t, os.SameFile(first, last))
			require.True(t, os.SameFile(first, copyMetadataTestInfo(t, donor)))
			require.False(t, os.SameFile(first, private))
		})
	}
}

func TestCopyFileMixedXAttrPoliciesKeepCopiesSeparate(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	source := filepath.Join(root, "source")
	require.NoError(t, os.WriteFile(source, []byte("contents"), 0o644))
	const attr = "user.layercopy-test"
	require.NoError(t, sysx.Setxattr(source, attr, []byte("source attribute"), 0))
	dest := t.TempDir()
	copier, err := NewCopier(Mount{Root: dest})
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, copier.Close()) })

	opts := CopyOptions{DisableSourceHardlinks: true, DisableXAttrs: true}
	require.NoError(t, copier.CopyFile(context.Background(), Mount{Root: root}, "/source", "/without", opts))
	opts.DisableXAttrs = false
	require.NoError(t, copier.CopyFile(context.Background(), Mount{Root: root}, "/source", "/with", opts))

	_, err = sysx.Getxattr(filepath.Join(dest, "without"), attr)
	require.ErrorIs(t, err, unix.ENODATA)
	value, err := sysx.Getxattr(filepath.Join(dest, "with"), attr)
	require.NoError(t, err)
	require.Equal(t, "source attribute", string(value))
	require.False(t, os.SameFile(copyMetadataTestInfo(t, filepath.Join(dest, "without")), copyMetadataTestInfo(t, filepath.Join(dest, "with"))))
}

func TestCopyFileMixedSourceIsolationKeepsPrivateCopy(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	source := filepath.Join(root, "source")
	require.NoError(t, os.WriteFile(source, []byte("contents"), 0o644))
	dest := t.TempDir()
	copier, err := NewCopier(Mount{Root: dest})
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, copier.Close()) })

	require.NoError(t, copier.CopyFile(context.Background(), Mount{Root: root}, "/source", "/linked", CopyOptions{}))
	require.NoError(t, copier.CopyFile(context.Background(), Mount{Root: root}, "/source", "/private", CopyOptions{DisableSourceHardlinks: true}))
	require.True(t, os.SameFile(copyMetadataTestInfo(t, source), copyMetadataTestInfo(t, filepath.Join(dest, "linked"))))
	require.False(t, os.SameFile(copyMetadataTestInfo(t, source), copyMetadataTestInfo(t, filepath.Join(dest, "private"))))
}

func copyMetadataTestInfo(t *testing.T, path string) os.FileInfo {
	t.Helper()
	info, err := os.Stat(path)
	require.NoError(t, err)
	return info
}
