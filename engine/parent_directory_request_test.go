package engine

import (
	"encoding/json"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/require"
)

func parentMetadataOpts() LocalImportOpts {
	return LocalImportOpts{Path: filepath.FromSlash("/"), ParentDirsOnly: true, IncludePatterns: []string{"a/b"}, ExcludePatterns: []string{"a/b/*"}}
}

func TestParentDirectoryMetadataRequestValidation(t *testing.T) {
	require.NoError(t, parentMetadataOpts().ValidateParentDirectoryMetadataRequest())
	for _, target := range []string{"", ".", "..", "../a", "/a", "a/../b", "a/./b", "a//b", "a/", "!a", "a*", "a?", "a[b]", "a^", `a\b`, " a", "a "} {
		t.Run(target, func(t *testing.T) {
			o := parentMetadataOpts()
			o.IncludePatterns, o.ExcludePatterns = []string{target}, []string{target + "/*"}
			require.Error(t, o.ValidateParentDirectoryMetadataRequest())
		})
	}
	for name, mutate := range map[string]func(*LocalImportOpts){
		"disabled":      func(o *LocalImportOpts) { o.ParentDirsOnly = false },
		"extra-include": func(o *LocalImportOpts) { o.IncludePatterns = append(o.IncludePatterns, "c") },
		"extra-exclude": func(o *LocalImportOpts) { o.ExcludePatterns = append(o.ExcludePatterns, "!a/b/secret") },
		"wrong-exclude": func(o *LocalImportOpts) { o.ExcludePatterns[0] = "other/*" },
		"follow":        func(o *LocalImportOpts) { o.FollowPaths = []string{} },
		"gitignore":     func(o *LocalImportOpts) { o.UseGitIgnore = true },
		"read":          func(o *LocalImportOpts) { o.ReadSingleFileOnly = true },
		"max-size":      func(o *LocalImportOpts) { o.MaxFileSize = 1 },
		"stat":          func(o *LocalImportOpts) { o.StatPathOnly = true },
		"stat-abs":      func(o *LocalImportOpts) { o.StatReturnAbsPath = true },
		"stat-resolve":  func(o *LocalImportOpts) { o.StatResolvePath = true },
		"abs":           func(o *LocalImportOpts) { o.GetAbsPathOnly = true },
		"glob":          func(o *LocalImportOpts) { o.GlobPattern = "*" },
		"search":        func(o *LocalImportOpts) { o.SearchOpts = &LocalSearchOpts{} },
	} {
		t.Run(name, func(t *testing.T) {
			o := parentMetadataOpts()
			mutate(&o)
			require.Error(t, o.ValidateParentDirectoryMetadataRequest())
		})
	}
}

func TestParentDirectoryMetadataWireAndOldClientFallback(t *testing.T) {
	want := parentMetadataOpts()
	var got LocalImportOpts
	require.NoError(t, got.FromGRPCMD(want.ToGRPCMD()))
	require.Equal(t, want, got)
	// A client with the prior JSON shape ignores the additive flag and still
	// receives the exact legacy source root and both filter patterns.
	var old struct {
		Path            string   `json:"path"`
		IncludePatterns []string `json:"include_patterns"`
		ExcludePatterns []string `json:"exclude_patterns"`
	}
	encoded, err := json.Marshal(want)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal(encoded, &old))
	require.Equal(t, want.Path, old.Path)
	require.Equal(t, want.IncludePatterns, old.IncludePatterns)
	require.Equal(t, want.ExcludePatterns, old.ExcludePatterns)
	md := want.ToGRPCMD()
	require.Equal(t, want.IncludePatterns, md.Get(localDirImportIncludePatternsMetaKey))
	require.Equal(t, want.ExcludePatterns, md.Get(localDirImportExcludePatternsMetaKey))
}
