package core

import (
	"context"
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestParseGitDiffNameStatus(t *testing.T) {
	tests := []struct {
		name      string
		output    string
		beforeDir string
		afterDir  string
		want      diffResult
	}{
		{
			name:      "empty output",
			output:    "",
			beforeDir: "/before",
			afterDir:  "/after",
			want:      diffResult{},
		},
		{
			name:      "added file",
			output:    "A\t/after/newfile.txt\n",
			beforeDir: "/before",
			afterDir:  "/after",
			want: diffResult{
				Added: []string{"newfile.txt"},
			},
		},
		{
			name:      "modified file",
			output:    "M\t/before/existing.txt\n",
			beforeDir: "/before",
			afterDir:  "/after",
			want: diffResult{
				Modified: []string{"existing.txt"},
			},
		},
		{
			name:      "deleted file",
			output:    "D\t/before/removed.txt\n",
			beforeDir: "/before",
			afterDir:  "/after",
			want: diffResult{
				Removed: []string{"removed.txt"},
			},
		},
		{
			name: "mixed changes",
			output: `A	/after/new.txt
M	/before/changed.txt
D	/before/deleted.txt
A	/after/subdir/another.txt
`,
			beforeDir: "/before",
			afterDir:  "/after",
			want: diffResult{
				Added:    []string{"new.txt", "subdir/another.txt"},
				Modified: []string{"changed.txt"},
				Removed:  []string{"deleted.txt"},
			},
		},
		{
			name:      "nested paths",
			output:    "A\t/after/a/b/c/deep.txt\n",
			beforeDir: "/before",
			afterDir:  "/after",
			want: diffResult{
				Added: []string{"a/b/c/deep.txt"},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parseGitDiffNameStatus([]byte(tt.output), tt.beforeDir, tt.afterDir)
			require.Equal(t, tt.want, got)
		})
	}
}

func TestCollectDirectories(t *testing.T) {
	// Create a temp directory structure
	root := t.TempDir()

	// Create: root/a/, root/a/b/, root/c/
	require.NoError(t, os.MkdirAll(filepath.Join(root, "a", "b"), 0755))
	require.NoError(t, os.MkdirAll(filepath.Join(root, "c"), 0755))
	// Create a file (should not be included)
	require.NoError(t, os.WriteFile(filepath.Join(root, "file.txt"), []byte("content"), 0644))

	dirs, err := collectDirectories(root)
	require.NoError(t, err)

	slices.Sort(dirs)
	require.Equal(t, []string{"a/", "a/b/", "c/"}, dirs)
}

func TestDiffDirectories(t *testing.T) {
	tests := []struct {
		name        string
		beforeDirs  []string
		afterDirs   []string
		wantAdded   []string
		wantRemoved []string
	}{
		{
			name:        "no changes",
			beforeDirs:  []string{"a/", "b/"},
			afterDirs:   []string{"a/", "b/"},
			wantAdded:   nil,
			wantRemoved: nil,
		},
		{
			name:        "added directory",
			beforeDirs:  []string{"a/"},
			afterDirs:   []string{"a/", "b/"},
			wantAdded:   []string{"b/"},
			wantRemoved: nil,
		},
		{
			name:        "removed directory",
			beforeDirs:  []string{"a/", "b/"},
			afterDirs:   []string{"a/"},
			wantAdded:   nil,
			wantRemoved: []string{"b/"},
		},
		{
			name:        "mixed changes",
			beforeDirs:  []string{"old/", "kept/"},
			afterDirs:   []string{"new/", "kept/"},
			wantAdded:   []string{"new/"},
			wantRemoved: []string{"old/"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			added, removed := diffDirectories(tt.beforeDirs, tt.afterDirs)
			require.Equal(t, tt.wantAdded, added)
			require.Equal(t, tt.wantRemoved, removed)
		})
	}
}

func TestRollupRemovedPaths(t *testing.T) {
	tests := []struct {
		name  string
		paths []string
		want  []string
	}{
		{
			name:  "empty",
			paths: nil,
			want:  nil,
		},
		{
			name:  "single file",
			paths: []string{"file.txt"},
			want:  []string{"file.txt"},
		},
		{
			name:  "single directory",
			paths: []string{"dir/"},
			want:  []string{"dir/"},
		},
		{
			name:  "directory hides children",
			paths: []string{"dir/", "dir/file.txt", "dir/subdir/", "dir/subdir/deep.txt"},
			want:  []string{"dir/"},
		},
		{
			name:  "mixed files and directories",
			paths: []string{"standalone.txt", "removed-dir/", "removed-dir/child.txt", "another.txt"},
			want:  []string{"another.txt", "removed-dir/", "standalone.txt"},
		},
		{
			name:  "nested directories",
			paths: []string{"a/", "a/b/", "a/b/c/", "a/b/c/file.txt"},
			want:  []string{"a/"},
		},
		{
			name:  "sibling directories",
			paths: []string{"a/", "a/file.txt", "b/", "b/file.txt"},
			want:  []string{"a/", "b/"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := rollupRemovedPaths(tt.paths)
			require.Equal(t, tt.want, got)
		})
	}
}

func TestGitDiffNameStatus_Integration(t *testing.T) {
	// Create two temp directories with different content
	beforeDir := t.TempDir()
	afterDir := t.TempDir()

	// Before: file1.txt, file2.txt, subdir/nested.txt
	require.NoError(t, os.WriteFile(filepath.Join(beforeDir, "file1.txt"), []byte("original"), 0644))
	require.NoError(t, os.WriteFile(filepath.Join(beforeDir, "file2.txt"), []byte("to be deleted"), 0644))
	require.NoError(t, os.MkdirAll(filepath.Join(beforeDir, "subdir"), 0755))
	require.NoError(t, os.WriteFile(filepath.Join(beforeDir, "subdir", "nested.txt"), []byte("nested"), 0644))

	// After: file1.txt (modified), file3.txt (new), subdir/nested.txt (unchanged)
	require.NoError(t, os.WriteFile(filepath.Join(afterDir, "file1.txt"), []byte("modified"), 0644))
	require.NoError(t, os.WriteFile(filepath.Join(afterDir, "file3.txt"), []byte("brand new"), 0644))
	require.NoError(t, os.MkdirAll(filepath.Join(afterDir, "subdir"), 0755))
	require.NoError(t, os.WriteFile(filepath.Join(afterDir, "subdir", "nested.txt"), []byte("nested"), 0644))

	ctx := context.Background()
	output, err := gitDiffNameStatus(ctx, beforeDir, afterDir)
	require.NoError(t, err)

	result := parseGitDiffNameStatus(output, beforeDir, afterDir)

	// Verify results
	slices.Sort(result.Added)
	slices.Sort(result.Modified)
	slices.Sort(result.Removed)

	require.Equal(t, []string{"file3.txt"}, result.Added)
	require.Equal(t, []string{"file1.txt"}, result.Modified)
	require.Equal(t, []string{"file2.txt"}, result.Removed)
}

func TestGitDiffQuiet_Integration(t *testing.T) {
	t.Run("identical directories", func(t *testing.T) {
		dir1 := t.TempDir()
		dir2 := t.TempDir()

		// Same content in both
		require.NoError(t, os.WriteFile(filepath.Join(dir1, "file.txt"), []byte("same"), 0644))
		require.NoError(t, os.WriteFile(filepath.Join(dir2, "file.txt"), []byte("same"), 0644))

		ctx := context.Background()
		identical, err := gitDiffQuiet(ctx, dir1, dir2)
		require.NoError(t, err)
		require.True(t, identical)
	})

	t.Run("different directories", func(t *testing.T) {
		dir1 := t.TempDir()
		dir2 := t.TempDir()

		// Different content
		require.NoError(t, os.WriteFile(filepath.Join(dir1, "file.txt"), []byte("before"), 0644))
		require.NoError(t, os.WriteFile(filepath.Join(dir2, "file.txt"), []byte("after"), 0644))

		ctx := context.Background()
		identical, err := gitDiffQuiet(ctx, dir1, dir2)
		require.NoError(t, err)
		require.False(t, identical)
	})

	t.Run("empty directories are identical", func(t *testing.T) {
		dir1 := t.TempDir()
		dir2 := t.TempDir()

		ctx := context.Background()
		identical, err := gitDiffQuiet(ctx, dir1, dir2)
		require.NoError(t, err)
		require.True(t, identical)
	})
}
