package cas

import (
	"testing"

	digest "github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestApplyDelta(t *testing.T) {
	t.Parallel()

	base := Manifest{
		Version: ManifestVersion,
		Scope:   ScopeKey(digest.FromString("scope").String()),
		Entries: map[string]Entry{
			"dir/file.txt": {
				Path:       "dir/file.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("old"),
			},
			"dir/symlink": {
				Path:       "dir/symlink",
				Kind:       EntrySymlink,
				LinkTarget: "file.txt",
			},
			"dir/hardlink": {
				Path:       "dir/hardlink",
				Kind:       EntryHardlink,
				LinkTarget: "file.txt",
			},
			"dir/sub/keep.txt": {
				Path:       "dir/sub/keep.txt",
				Kind:       EntryFile,
				BlobDigest: digest.FromString("keep"),
			},
		},
	}

	baseRoot, err := RootDigest(base)
	assert.NilError(t, err)
	base.RootDigest = baseRoot

	delta := ManifestDelta{
		Upserts: map[string]Entry{
			"dir/file.txt": {
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("new"),
			},
			"dir/new.txt": {
				Kind:       EntryFile,
				Mode:       0o600,
				BlobDigest: digest.FromString("new-file"),
			},
			"dir/symlink": {
				Kind:       EntrySymlink,
				Mode:       0o777,
				LinkTarget: "new.txt",
			},
			"dir/hardlink": {
				Kind:       EntryHardlink,
				Mode:       0o644,
				LinkTarget: "new.txt",
			},
		},
		Deletes: map[string]struct{}{
			"dir/sub": {},
		},
		None: map[string]struct{}{
			"dir/unchanged": {},
		},
	}

	applied, err := ApplyDelta(base, delta)
	assert.NilError(t, err)

	assert.Assert(t, is.Len(applied.Entries, 4))
	assert.Equal(t, applied.Entries["dir/file.txt"].BlobDigest, digest.FromString("new"))
	assert.Equal(t, applied.Entries["dir/new.txt"].BlobDigest, digest.FromString("new-file"))
	assert.Equal(t, applied.Entries["dir/symlink"].LinkTarget, "new.txt")
	assert.Equal(t, applied.Entries["dir/hardlink"].LinkTarget, "new.txt")
	_, deletedStillPresent := applied.Entries["dir/sub/keep.txt"]
	assert.Assert(t, !deletedStillPresent)

	assert.Assert(t, applied.RootDigest != base.RootDigest)
}

func TestApplyDeltaRejectsPathConflicts(t *testing.T) {
	t.Parallel()

	_, err := ApplyDelta(Manifest{}, ManifestDelta{
		Upserts: map[string]Entry{"dir/file.txt": {Kind: EntryFile}},
		Deletes: map[string]struct{}{"dir/file.txt": {}},
	})
	assert.Assert(t, is.ErrorContains(err, "cannot be both upsert and delete"))
}
