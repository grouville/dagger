package core

import (
	"context"
	"os"
	"path/filepath"
	"slices"
	"testing"

	"github.com/stretchr/testify/require"
)

func joinZ(parts ...string) []byte {
	var b []byte
	for _, p := range parts {
		b = append(b, p...)
		b = append(b, 0)
	}
	return b
}

func TestParseGitDiffNameStatus(t *testing.T) {
	beforeDir := "/before"
	afterDir := "/after"

	tests := []struct {
		name   string
		output []byte
		want   diffResult
	}{
		{
			name:   "empty output",
			output: nil,
			want:   diffResult{},
		},
		{
			name: "mixed changes",
			output: joinZ(
				"A", afterDir+"/new.txt",
				"M", beforeDir+"/changed.txt",
				"D", beforeDir+"/deleted.txt",
				"A", afterDir+"/a/b/deep.txt",
			),
			want: diffResult{
				Added:    []string{"new.txt", "a/b/deep.txt"},
				Modified: []string{"changed.txt"},
				Removed:  []string{"deleted.txt"},
			},
		},
		{
			name:   "renamed file",
			output: joinZ("R100", beforeDir+"/old.txt", afterDir+"/new.txt"),
			want: diffResult{
				Added:   []string{"new.txt"},
				Removed: []string{"old.txt"},
			},
		},
		{
			name:   "copied file",
			output: joinZ("C100", beforeDir+"/base.txt", afterDir+"/copy.txt"),
			want: diffResult{
				Added: []string{"copy.txt"},
			},
		},
		{
			name:   "file with newline",
			output: joinZ("A", afterDir+"/line\nbreak.txt"),
			want: diffResult{
				Added: []string{"line\nbreak.txt"},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parseGitDiffNameStatus(tt.output, beforeDir, afterDir)
			require.Equal(t, tt.want, got)
		})
	}
}

func TestCollectDirectories(t *testing.T) {
	root := t.TempDir()
	require.NoError(t, os.MkdirAll(filepath.Join(root, "a", "b"), 0755))
	require.NoError(t, os.MkdirAll(filepath.Join(root, "c"), 0755))
	require.NoError(t, os.WriteFile(filepath.Join(root, "file.txt"), []byte("."), 0644))

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
			name:       "no changes",
			beforeDirs: []string{"a/", "b/"},
			afterDirs:  []string{"a/", "b/"},
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
			name: "empty",
		},
		{
			name:  "directory hides children",
			paths: []string{"dir/", "dir/file.txt", "dir/sub/", "dir/sub/deep.txt"},
			want:  []string{"dir/"},
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

func TestGitDiff_Integration(t *testing.T) {
	beforeDir := t.TempDir()
	afterDir := t.TempDir()

	// Before: file1.txt, file2.txt, subdir/nested.txt
	require.NoError(t, os.WriteFile(filepath.Join(beforeDir, "file1.txt"), []byte("original"), 0644))
	require.NoError(t, os.WriteFile(filepath.Join(beforeDir, "file2.txt"), []byte("deleted"), 0644))
	require.NoError(t, os.MkdirAll(filepath.Join(beforeDir, "subdir"), 0755))
	require.NoError(t, os.WriteFile(filepath.Join(beforeDir, "subdir", "nested.txt"), []byte("nested"), 0644))

	// After: file1.txt (modified), file3.txt (new), subdir/nested.txt (unchanged)
	require.NoError(t, os.WriteFile(filepath.Join(afterDir, "file1.txt"), []byte("modified"), 0644))
	require.NoError(t, os.WriteFile(filepath.Join(afterDir, "file3.txt"), []byte("new"), 0644))
	require.NoError(t, os.MkdirAll(filepath.Join(afterDir, "subdir"), 0755))
	require.NoError(t, os.WriteFile(filepath.Join(afterDir, "subdir", "nested.txt"), []byte("nested"), 0644))

	ctx := context.Background()

	// Test gitDiffNameStatus + parse
	output, err := gitDiffNameStatus(ctx, beforeDir, afterDir)
	require.NoError(t, err)
	result := parseGitDiffNameStatus(output, beforeDir, afterDir)
	slices.Sort(result.Added)
	slices.Sort(result.Modified)
	slices.Sort(result.Removed)
	require.Equal(t, []string{"file3.txt"}, result.Added)
	require.Equal(t, []string{"file1.txt"}, result.Modified)
	require.Equal(t, []string{"file2.txt"}, result.Removed)

	// Test gitDiffQuiet
	identical, err := gitDiffQuiet(ctx, beforeDir, afterDir)
	require.NoError(t, err)
	require.False(t, identical)

	identical, err = gitDiffQuiet(ctx, beforeDir, beforeDir)
	require.NoError(t, err)
	require.True(t, identical)
}
