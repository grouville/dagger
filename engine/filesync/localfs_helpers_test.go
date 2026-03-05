package filesync

import (
	"os"
	"path/filepath"
	"testing"

	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestExpandCopyOnlySetAddsParents(t *testing.T) {
	t.Parallel()

	got := expandCopyOnlySet(map[string]struct{}{
		"a/b/c.txt": {},
		"top.txt":   {},
	})

	want := map[string]struct{}{
		"a":         {},
		"a/b":       {},
		"a/b/c.txt": {},
		"top.txt":   {},
	}
	assert.DeepEqual(t, got, want)
}

func TestProjectDeleteTargets(t *testing.T) {
	t.Parallel()

	got := projectDeleteTargets(map[string]struct{}{
		"/repo/a":         {},
		"/repo/a/b/c.txt": {},
		"/repo/a/b.txt":   {},
		"/other/skip.txt": {},
	}, "/repo")

	assert.DeepEqual(t, got, []string{"a/b/c.txt", "a/b.txt", "a"})
}

func TestProjectDeleteTargetsRoot(t *testing.T) {
	t.Parallel()

	got := projectDeleteTargets(map[string]struct{}{
		"/repo": {},
	}, "/repo")

	assert.DeepEqual(t, got, []string{"."})
}

func TestRemoveProjectedPath(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	assert.NilError(t, os.MkdirAll(filepath.Join(root, "a", "b"), 0o755))
	assert.NilError(t, os.WriteFile(filepath.Join(root, "a", "b", "c.txt"), []byte("x"), 0o644))
	assert.NilError(t, os.WriteFile(filepath.Join(root, "top.txt"), []byte("y"), 0o644))

	assert.NilError(t, removeProjectedPath(root, "a"))
	_, err := os.Stat(filepath.Join(root, "a"))
	assert.Assert(t, is.ErrorIs(err, os.ErrNotExist))
	_, err = os.Stat(filepath.Join(root, "top.txt"))
	assert.NilError(t, err)

	assert.NilError(t, removeProjectedPath(root, "."))
	entries, err := os.ReadDir(root)
	assert.NilError(t, err)
	assert.Equal(t, len(entries), 0)
}

func TestRemoveProjectedPathRejectsEscape(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	err := removeProjectedPath(root, "../escape")
	assert.Assert(t, err != nil)
}
