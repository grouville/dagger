package filesync

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/dagger/dagger/engine/filesync/cas"
	digest "github.com/opencontainers/go-digest"
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

func TestShouldUseParentFromScopeHead(t *testing.T) {
	t.Parallel()

	assert.Assert(t, shouldUseParentFromScopeHead(cas.ScopeHead{ChainDepth: 0}))
	assert.Assert(t, shouldUseParentFromScopeHead(cas.ScopeHead{ChainDepth: maxParentMaterializeChainDepth - 1}))
	assert.Assert(t, !shouldUseParentFromScopeHead(cas.ScopeHead{ChainDepth: maxParentMaterializeChainDepth}))
}

func TestLocalFSSharedStateScopeHeadCAS(t *testing.T) {
	t.Parallel()

	state := &localFSSharedState{
		scopeHeads: &runtimeScopeHeadStore{
			heads: map[cas.ScopeKey]cas.ScopeHead{},
		},
	}
	scope := cas.ScopeKey("sha256:scope")

	head1 := cas.ScopeHead{
		Scope:         scope,
		RootDigest:    digest.FromString("root-1"),
		MaterialRefID: "ref-1",
		Generation:    1,
		ChainDepth:    1,
	}
	assert.NilError(t, state.saveScopeHead(head1, 0))

	loaded, ok := state.loadScopeHead(scope)
	assert.Assert(t, ok)
	assert.DeepEqual(t, loaded, head1)

	head2 := cas.ScopeHead{
		Scope:         scope,
		RootDigest:    digest.FromString("root-2"),
		MaterialRefID: "ref-2",
		Generation:    2,
		ChainDepth:    2,
	}
	assert.NilError(t, state.saveScopeHead(head2, 1))

	err := state.saveScopeHead(head2, 0)
	assert.Assert(t, is.ErrorContains(err, "generation mismatch"))
}
