package cas

import (
	"testing"

	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestScopeKeyDeterministic(t *testing.T) {
	t.Parallel()

	scopeA := ScopeInput{
		ClientPath:      "/work/repo/./",
		IncludePatterns: nil,
		ExcludePatterns: nil,
		GitIgnore:       true,
		RelativePath:    ".",
	}
	scopeB := ScopeInput{
		ClientPath:      "/work/repo",
		IncludePatterns: []string{},
		ExcludePatterns: []string{},
		GitIgnore:       true,
		RelativePath:    "",
	}

	keyA, err := NewScopeKey(scopeA)
	assert.NilError(t, err)

	keyA2, err := NewScopeKey(scopeA)
	assert.NilError(t, err)

	keyB, err := NewScopeKey(scopeB)
	assert.NilError(t, err)

	assert.Equal(t, keyA, keyA2)
	assert.Equal(t, keyA, keyB)
}

func TestScopeKeyChangesWhenFiltersChange(t *testing.T) {
	t.Parallel()

	base := ScopeInput{
		ClientPath:      "/work/repo",
		IncludePatterns: []string{"core/**"},
		ExcludePatterns: []string{"**/*.tmp"},
		GitIgnore:       false,
	}

	keyA, err := NewScopeKey(base)
	assert.NilError(t, err)

	changed := base
	changed.IncludePatterns = []string{"engine/**"}

	keyB, err := NewScopeKey(changed)
	assert.NilError(t, err)

	assert.Assert(t, keyA != keyB)
}

func TestNormalizeScopePath(t *testing.T) {
	t.Parallel()

	path, err := NormalizeScopePath("/repo/../repo/./core")
	assert.NilError(t, err)
	assert.Equal(t, "/repo/core", path)

	_, err = NormalizeScopePath("repo/core")
	assert.Assert(t, is.ErrorContains(err, "must be absolute"))
}

func TestNormalizeRelativePath(t *testing.T) {
	t.Parallel()

	path, err := NormalizeRelativePath("sdk/../engine/./filesync")
	assert.NilError(t, err)
	assert.Equal(t, "engine/filesync", path)

	path, err = NormalizeRelativePath(".")
	assert.NilError(t, err)
	assert.Equal(t, "", path)

	_, err = NormalizeRelativePath("../escape")
	assert.Assert(t, is.ErrorContains(err, "escapes root"))

	_, err = NormalizeRelativePath("/abs")
	assert.Assert(t, is.ErrorContains(err, "must not be absolute"))
}

func TestNormalizeEntryPath(t *testing.T) {
	t.Parallel()

	path, err := NormalizeEntryPath("core\\integration\\..\\filesync")
	assert.NilError(t, err)
	assert.Equal(t, "core/filesync", path)

	_, err = NormalizeEntryPath("")
	assert.Assert(t, is.ErrorContains(err, "entry path is empty"))

	_, err = NormalizeEntryPath("../escape")
	assert.Assert(t, is.ErrorContains(err, "escapes root"))
}
