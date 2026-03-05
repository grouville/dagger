package cas

import (
	"testing"

	digest "github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestRootIndexWriteRead(t *testing.T) {
	t.Parallel()

	store := newFakeMetadataStore()
	index := RootIndexStore{Store: store}
	root := digest.FromString("root-a")

	refA := store.newRef("ref-a")
	refB := store.newRef("ref-b")

	assert.NilError(t, index.Save(refA, root))
	assert.NilError(t, index.Save(refB, root))

	ids, err := index.Resolve(t.Context(), root)
	assert.NilError(t, err)
	assert.DeepEqual(t, ids, []string{"ref-a", "ref-b"})
}

func TestRootIndexIdempotentReinsert(t *testing.T) {
	t.Parallel()

	store := newFakeMetadataStore()
	index := RootIndexStore{Store: store}
	root := digest.FromString("root-a")

	ref := store.newRef("ref-a")
	assert.NilError(t, index.Save(ref, root))
	assert.NilError(t, index.Save(ref, root))

	ids, err := index.Resolve(t.Context(), root)
	assert.NilError(t, err)
	assert.Assert(t, is.Len(ids, 1))
	assert.Equal(t, ids[0], "ref-a")
}
