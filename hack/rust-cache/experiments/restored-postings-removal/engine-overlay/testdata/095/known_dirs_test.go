//go:build linux

package layercopy

import (
	"context"
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/containerd/containerd/v2/core/mount"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

func TestKnownDirectoryReappliesSourceMetadata(t *testing.T) {
	for _, split := range []bool{false, true} {
		t.Run(fmt.Sprint(split), func(t *testing.T) {
			root := t.TempDir()
			view := filepath.Join(root, "view")
			upper := view
			require.NoError(t, os.Mkdir(view, 0755))
			destinationMount := Mount{Root: view}
			if split {
				upper = filepath.Join(root, "upper")
				require.NoError(t, os.Mkdir(upper, 0755))
				destinationMount.Mount = &mount.Mount{Type: "overlay", Options: []string{"upperdir=" + upper, "userxattr"}}
			}
			destination, err := newDestination(destinationMount)
			require.NoError(t, err)
			source := filepath.Join(root, "source")
			require.NoError(t, os.Mkdir(source, 0751))
			hasXattrs := unix.Setxattr(source, "user.layercopy-known", []byte("old"), 0) == nil
			for generation, mode := range []os.FileMode{0751, 0701} {
				stamp := time.Unix(1234567890+int64(generation), 123456789)
				require.NoError(t, os.Chmod(source, mode))
				require.NoError(t, os.Chtimes(source, stamp, stamp))
				if hasXattrs {
					require.NoError(t, unix.Setxattr(source, "user.layercopy-known", []byte(fmt.Sprint(generation)), 0))
				}
				info, err := os.Stat(source)
				require.NoError(t, err)
				_, _, err = destination.ensureDir("/node", &sourceEntry{RealPath: source, Info: info}, CopyOptions{}, true)
				require.NoError(t, err)
				got, err := os.Stat(filepath.Join(upper, "node"))
				require.NoError(t, err)
				require.Equal(t, mode, got.Mode().Perm())
				require.Equal(t, stamp, got.ModTime())
				if hasXattrs {
					data := make([]byte, 32)
					n, err := unix.Getxattr(filepath.Join(upper, "node"), "user.layercopy-known", data)
					require.NoError(t, err)
					require.Equal(t, fmt.Sprint(generation), string(data[:n]))
				}
			}
		})
	}
}

func TestKnownDirectoryRemovalResolvesReplacementSymlink(t *testing.T) {
	root := t.TempDir()
	destination, err := newDestination(Mount{Root: root})
	require.NoError(t, err)
	_, _, err = destination.ensureDir("/node", nil, CopyOptions{}, true)
	require.NoError(t, err)
	_, _, err = destination.ensureDir("/other", nil, CopyOptions{}, true)
	require.NoError(t, err)
	require.NoError(t, destination.removeAll(filepath.Join(root, "node"), true))
	require.NoError(t, os.Symlink("other", filepath.Join(root, "node")))
	mode := os.FileMode(0751)
	rel, _, err := destination.ensureDir("/node", nil, CopyOptions{Mode: &mode}, true)
	require.NoError(t, err)
	require.Equal(t, "other", rel)
	link, err := os.Readlink(filepath.Join(root, "node"))
	require.NoError(t, err)
	require.Equal(t, "other", link)
	info, err := os.Stat(filepath.Join(root, "other"))
	require.NoError(t, err)
	require.Equal(t, mode, info.Mode().Perm())
}

func TestKnownDirectoryHiddenUpperReplacementDoesNotReuseDescendants(t *testing.T) {
	root := t.TempDir()
	view, upper, source := filepath.Join(root, "view"), filepath.Join(root, "upper"), filepath.Join(root, "source")
	for _, directory := range []string{view, upper, source} {
		require.NoError(t, os.Mkdir(directory, 0755))
	}
	require.NoError(t, os.WriteFile(filepath.Join(view, "node"), []byte("lower file"), 0644))
	require.NoError(t, os.Symlink("other", filepath.Join(source, "link")))
	copier, err := NewCopier(Mount{Root: view, Mount: &mount.Mount{Type: "overlay", Options: []string{"upperdir=" + upper, "userxattr"}}})
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, copier.Close()) })
	require.NoError(t, copier.Mkdir(t.Context(), "/node", CopyOptions{ReplaceExisting: true}))
	require.NoError(t, copier.Mkdir(t.Context(), "/node/child", CopyOptions{}))
	require.NoError(t, copier.Mkdir(t.Context(), "/other/child", CopyOptions{}))
	require.NoError(t, copier.Copy(t.Context(), Mount{Root: source}, "/link", "/node", CopyOptions{ReplaceExisting: true}))
	link, err := os.Readlink(filepath.Join(upper, "node"))
	require.NoError(t, err)
	require.Equal(t, "other", link)
	before, err := os.Stat(filepath.Join(upper, "other", "child"))
	require.NoError(t, err)
	mode := os.FileMode(0701)
	_, _, err = copier.dest.ensureDir("/node/child", nil, CopyOptions{Mode: &mode}, true)
	require.Error(t, err, "the lower view still has a file at node; stale descendants must not bypass resolution")
	after, err := os.Stat(filepath.Join(upper, "other", "child"))
	require.NoError(t, err)
	require.Equal(t, before.Mode(), after.Mode())
}

func BenchmarkCopyKnownIncrementalDirectories(b *testing.B) {
	for _, count := range []int{1, 128, 1026} {
		for _, split := range []bool{false, true} {
			b.Run(fmt.Sprintf("crates=%d/split=%t", count, split), func(b *testing.B) {
				root := b.TempDir()
				source := filepath.Join(root, "source")
				require.NoError(b, os.Mkdir(source, 0755))
				var includes []string
				for i := range count {
					token := fmt.Sprintf("%x", sha256.Sum256([]byte(fmt.Sprint(i))))
					directory := filepath.Join(source, token, "session")
					require.NoError(b, os.MkdirAll(directory, 0755))
					for _, name := range []string{"dep-graph.bin", "query-cache.bin", "work-products.bin"} {
						require.NoError(b, os.WriteFile(filepath.Join(directory, name), []byte("state"), 0644))
					}
					includes = append(includes, token+"/**")
				}
				opts := CopyOptions{Filter: Filter{Include: includes}, CopyDirContents: true, ReplaceExisting: true}
				b.ReportAllocs()
				b.ResetTimer()
				for i := 0; i < b.N; i++ {
					b.StopTimer()
					attempt := filepath.Join(root, fmt.Sprint(i))
					view := filepath.Join(attempt, "view")
					upper := view
					require.NoError(b, os.MkdirAll(view, 0755))
					destinationMount := Mount{Root: view}
					if split {
						upper = filepath.Join(attempt, "upper")
						require.NoError(b, os.Mkdir(upper, 0755))
						destinationMount.Mount = &mount.Mount{Type: "overlay", Options: []string{"upperdir=" + upper, "userxattr"}}
					}
					b.StartTimer()
					copier, err := NewCopier(destinationMount)
					require.NoError(b, err)
					require.NoError(b, copier.Copy(context.Background(), Mount{Root: source}, "/", "/incremental", opts))
					require.NoError(b, copier.Close())
					b.StopTimer()
					require.NoError(b, os.RemoveAll(attempt))
					b.StartTimer()
				}
			})
		}
	}
}
