package cas

import (
	"testing"

	digest "github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
	is "gotest.tools/v3/assert/cmp"
)

func TestManifestSerializationStable(t *testing.T) {
	t.Parallel()

	first := Manifest{
		Version: ManifestVersion,
		Scope:   ScopeKey("sha256:scope"),
		Entries: map[string]Entry{
			"b/path.txt": {
				Path:       "b/path.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("b"),
				XAttrs: map[string][]byte{
					"user.k2": []byte("v2"),
					"user.k1": []byte("v1"),
				},
			},
			"a/path.txt": {
				Path:       "a/path.txt",
				Kind:       EntryFile,
				Mode:       0o600,
				BlobDigest: digest.FromString("a"),
			},
		},
	}

	second := Manifest{
		Version: ManifestVersion,
		Scope:   ScopeKey("sha256:scope"),
		Entries: map[string]Entry{
			"a/path.txt": {
				Path:       "a/path.txt",
				Kind:       EntryFile,
				Mode:       0o600,
				BlobDigest: digest.FromString("a"),
			},
			"b/path.txt": {
				Path:       "b/path.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				BlobDigest: digest.FromString("b"),
				XAttrs: map[string][]byte{
					"user.k1": []byte("v1"),
					"user.k2": []byte("v2"),
				},
			},
		},
	}

	firstPayload, err := first.CanonicalBytes()
	assert.NilError(t, err)

	secondPayload, err := second.CanonicalBytes()
	assert.NilError(t, err)

	assert.DeepEqual(t, firstPayload, secondPayload)
}

func TestManifestRoundtrip(t *testing.T) {
	t.Parallel()

	manifest := Manifest{
		Version:    ManifestVersion,
		Scope:      ScopeKey("sha256:scope"),
		RootDigest: digest.FromString("root"),
		Entries: map[string]Entry{
			"dir/file.txt": {
				Path:       "dir/file.txt",
				Kind:       EntryFile,
				Mode:       0o644,
				UID:        1000,
				GID:        1000,
				Size:       12,
				BlobDigest: digest.FromString("file-bytes"),
			},
			"dir/link": {
				Path:       "dir/link",
				Kind:       EntrySymlink,
				Mode:       0o777,
				LinkTarget: "file.txt",
			},
		},
	}

	payloadA, err := manifest.CanonicalBytes()
	assert.NilError(t, err)

	parsed, err := ParseManifest(payloadA)
	assert.NilError(t, err)

	payloadB, err := parsed.CanonicalBytes()
	assert.NilError(t, err)

	assert.DeepEqual(t, payloadA, payloadB)
	assert.Equal(t, manifest.Version, parsed.Version)
	assert.Equal(t, manifest.Scope, parsed.Scope)
	assert.Equal(t, manifest.RootDigest, parsed.RootDigest)
	assert.Assert(t, is.Len(parsed.Entries, 2))
	assert.Equal(t, parsed.Entries["dir/file.txt"].BlobDigest, manifest.Entries["dir/file.txt"].BlobDigest)
	assert.Equal(t, parsed.Entries["dir/link"].LinkTarget, "file.txt")
}

func TestManifestRejectsInvalidEntryPath(t *testing.T) {
	t.Parallel()

	manifest := Manifest{
		Version: ManifestVersion,
		Scope:   ScopeKey("sha256:scope"),
		Entries: map[string]Entry{
			"../escape": {
				Path: "../escape",
				Kind: EntryFile,
			},
		},
	}

	_, err := manifest.CanonicalBytes()
	assert.Assert(t, is.ErrorContains(err, "escapes root"))
}
