package cas

import (
	"testing"

	digest "github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestMaterializePlanMinimalOneFileModify(t *testing.T) {
	t.Parallel()

	previous := Manifest{
		Entries: map[string]Entry{
			"dir/a.txt": {Path: "dir/a.txt", Kind: EntryFile, BlobDigest: digest.FromString("a1")},
			"dir/b.txt": {Path: "dir/b.txt", Kind: EntryFile, BlobDigest: digest.FromString("b1")},
		},
	}
	next := Manifest{
		Entries: map[string]Entry{
			"dir/a.txt": {Path: "dir/a.txt", Kind: EntryFile, BlobDigest: digest.FromString("a2")},
			"dir/b.txt": {Path: "dir/b.txt", Kind: EntryFile, BlobDigest: digest.FromString("b1")},
		},
	}

	plan, err := BuildMaterializePlan(previous, next)
	assert.NilError(t, err)
	assert.Assert(t, is.Len(plan.Deletes, 0))
	assert.Assert(t, is.Len(plan.Upserts, 1))
	assert.Equal(t, plan.Upserts[0].Path, "dir/a.txt")
}

func TestMaterializePlanDeleteHeavy(t *testing.T) {
	t.Parallel()

	previous := Manifest{
		Entries: map[string]Entry{
			"dir/sub/a.txt": {Path: "dir/sub/a.txt", Kind: EntryFile, BlobDigest: digest.FromString("a")},
			"dir/sub/b.txt": {Path: "dir/sub/b.txt", Kind: EntryFile, BlobDigest: digest.FromString("b")},
			"dir/c.txt":     {Path: "dir/c.txt", Kind: EntryFile, BlobDigest: digest.FromString("c")},
		},
	}
	next := Manifest{
		Entries: map[string]Entry{
			"dir/c.txt": {Path: "dir/c.txt", Kind: EntryFile, BlobDigest: digest.FromString("c")},
		},
	}

	plan, err := BuildMaterializePlan(previous, next)
	assert.NilError(t, err)
	assert.Assert(t, is.Len(plan.Upserts, 0))
	assert.DeepEqual(t, plan.Deletes, []string{"dir/sub/a.txt", "dir/sub/b.txt"})
}
