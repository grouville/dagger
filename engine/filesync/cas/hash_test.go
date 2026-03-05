package cas

import (
	"testing"

	digest "github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
)

func TestManifestDigestDeterministic(t *testing.T) {
	t.Parallel()

	first := Manifest{
		Entries: map[string]Entry{
			"a/file.txt": {
				Path:       "a/file.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("hello"),
			},
			"b/file.txt": {
				Path:       "b/file.txt",
				Kind:       EntryFile,
				Mode:       0o600,
				BlobDigest: digest.FromString("world"),
			},
		},
	}

	second := Manifest{
		Entries: map[string]Entry{
			"b/file.txt": {
				Path:       "b/file.txt",
				Kind:       EntryFile,
				Mode:       0o600,
				BlobDigest: digest.FromString("world"),
			},
			"a/file.txt": {
				Path:       "a/file.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("hello"),
			},
		},
	}

	firstDigest, err := RootDigest(first)
	assert.NilError(t, err)

	secondDigest, err := RootDigest(second)
	assert.NilError(t, err)

	assert.Equal(t, firstDigest, secondDigest)
}

func TestManifestDigestChangesOnMetadataChange(t *testing.T) {
	t.Parallel()

	base := Manifest{
		Entries: map[string]Entry{
			"dir/file.txt": {
				Path:       "dir/file.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("same-content"),
			},
		},
	}

	baseDigest, err := RootDigest(base)
	assert.NilError(t, err)

	changed := Manifest{
		Entries: map[string]Entry{
			"dir/file.txt": {
				Path:       "dir/file.txt",
				Kind:       EntryFile,
				Mode:       0o755, // metadata-only change
				BlobDigest: digest.FromString("same-content"),
			},
		},
	}

	changedDigest, err := RootDigest(changed)
	assert.NilError(t, err)

	assert.Assert(t, baseDigest != changedDigest)
}

func TestRenameReusesBlobDigestButChangesRoot(t *testing.T) {
	t.Parallel()

	blob := digest.FromString("same-file")

	original := Manifest{
		Entries: map[string]Entry{
			"old/name.txt": {
				Path:       "old/name.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: blob,
			},
		},
	}

	renamed := Manifest{
		Entries: map[string]Entry{
			"new/name.txt": {
				Path:       "new/name.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: blob,
			},
		},
	}

	originalRoot, err := RootDigest(original)
	assert.NilError(t, err)

	renamedRoot, err := RootDigest(renamed)
	assert.NilError(t, err)

	assert.Assert(t, originalRoot != renamedRoot)
	assert.Equal(t, original.Entries["old/name.txt"].BlobDigest, renamed.Entries["new/name.txt"].BlobDigest)
}
