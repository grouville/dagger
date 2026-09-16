//go:build linux

package layercopy

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCopyToEmptyRejectsLaterMutations(t *testing.T) {
	t.Parallel()
	for _, fail := range []bool{false, true} {
		name := "success"
		if fail {
			name = "failure"
		}
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			ctx := context.Background()
			source := t.TempDir()
			require.NoError(t, os.WriteFile(filepath.Join(source, "file"), []byte("contents"), 0o644))
			destination := t.TempDir()
			copier, err := NewCopier(Mount{Root: destination})
			require.NoError(t, err)
			opts := CopyOptions{CopyDirContents: true, DisableSourceHardlinks: true, DisableXAttrs: true}
			var materialize FreshFileMaterializer
			wantErr := errors.New("materialization failed")
			if fail {
				materialize = func(string, string, os.FileInfo) (bool, error) { return false, wantErr }
			}
			src := Mount{Root: source}
			err = copier.CopyToEmpty(ctx, src, "/", opts, materialize)
			if fail {
				require.ErrorIs(t, err, wantErr)
			} else {
				require.NoError(t, err)
			}
			require.NoError(t, copier.Close())
			require.ErrorContains(t, copier.Copy(ctx, src, "/", "/", opts), "cannot reuse")
			require.ErrorContains(t, copier.CopyFile(ctx, src, "/file", "/file", opts), "cannot reuse")
			require.ErrorContains(t, copier.Mkdir(ctx, "/later", opts), "cannot reuse")
			_, err = copier.MaterializeDestDir(ctx, "/later")
			require.ErrorContains(t, err, "cannot reuse")
			require.ErrorContains(t, copier.CopyToEmpty(ctx, src, "/", opts, nil), "unused copier")
			_, err = os.Stat(filepath.Join(destination, "later"))
			require.ErrorIs(t, err, os.ErrNotExist)
		})
	}
}

func TestCopyToEmptyRequiresPrivateEmptyDestination(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	source := Mount{Root: t.TempDir()}
	opts := CopyOptions{CopyDirContents: true, DisableSourceHardlinks: true, DisableXAttrs: true}

	t.Run("existing destination", func(t *testing.T) {
		destination := t.TempDir()
		path := filepath.Join(destination, "existing")
		require.NoError(t, os.WriteFile(path, []byte("untouched"), 0o644))
		copier, err := NewCopier(Mount{Root: destination})
		require.NoError(t, err)
		require.ErrorContains(t, copier.CopyToEmpty(ctx, source, "/", opts, nil), "empty destination")
		contents, err := os.ReadFile(path)
		require.NoError(t, err)
		require.Equal(t, "untouched", string(contents))
	})
	t.Run("previously used copier", func(t *testing.T) {
		copier, err := NewCopier(Mount{Root: t.TempDir()})
		require.NoError(t, err)
		require.NoError(t, copier.Mkdir(ctx, "/", CopyOptions{}))
		require.ErrorContains(t, copier.CopyToEmpty(ctx, source, "/", opts, nil), "unused copier")
	})
	mode := os.FileMode(0o600)
	for name, invalid := range map[string]CopyOptions{
		"source hardlinks": {DisableXAttrs: true},
		"xattrs":           {DisableSourceHardlinks: true},
		"replacement":      {DisableSourceHardlinks: true, DisableXAttrs: true, ReplaceExisting: true},
		"mode override":    {DisableSourceHardlinks: true, DisableXAttrs: true, Mode: &mode},
		"owner override":   {DisableSourceHardlinks: true, DisableXAttrs: true, Chown: &Ownership{}},
	} {
		t.Run(name, func(t *testing.T) {
			copier, err := NewCopier(Mount{Root: t.TempDir()})
			require.NoError(t, err)
			require.ErrorContains(t, copier.CopyToEmpty(ctx, source, "/", invalid, nil), "isolated files")
		})
	}
}

func TestCopyToEmptyDisabledHardlinksRemainIndependent(t *testing.T) {
	t.Parallel()
	source := t.TempDir()
	sourceA := filepath.Join(source, "a")
	require.NoError(t, os.WriteFile(sourceA, []byte("contents"), 0o644))
	require.NoError(t, os.Link(sourceA, filepath.Join(source, "b")))
	destination := t.TempDir()
	copier, err := NewCopier(Mount{Root: destination})
	require.NoError(t, err)
	lookups, materializations := 0, 0
	require.NoError(t, copier.CopyToEmpty(context.Background(), Mount{Root: source}, "/", CopyOptions{
		CopyDirContents:        true,
		DisableHardlinks:       true,
		DisableSourceHardlinks: true,
		DisableXAttrs:          true,
		ImmutableFileSource: func(string, os.FileInfo) (string, error) {
			lookups++
			return sourceA, nil
		},
	}, func(string, string, os.FileInfo) (bool, error) {
		materializations++
		return false, nil
	}))
	require.NoError(t, copier.Close())
	require.Zero(t, lookups)
	require.Equal(t, 2, materializations)
	a := copyMetadataTestInfo(t, filepath.Join(destination, "a"))
	b := copyMetadataTestInfo(t, filepath.Join(destination, "b"))
	require.False(t, os.SameFile(a, b))
	require.False(t, os.SameFile(a, copyMetadataTestInfo(t, sourceA)))
	require.False(t, os.SameFile(b, copyMetadataTestInfo(t, sourceA)))
}
