package cas

import digest "github.com/opencontainers/go-digest"

// ScopeKey identifies one filesync scope (path + filters + context mode).
type ScopeKey string

func (k ScopeKey) String() string {
	return string(k)
}

// ManifestVersion is the first persisted manifest format.
const ManifestVersion uint32 = 1

type EntryKind uint8

const (
	EntryFile EntryKind = iota + 1
	EntryDir
	EntrySymlink
	EntryHardlink
)

// Entry is one canonical path entry in a manifest.
type Entry struct {
	Path       string
	Kind       EntryKind
	Mode       uint32
	UID        uint32
	GID        uint32
	Size       int64
	LinkTarget string
	BlobDigest digest.Digest
	XAttrs     map[string][]byte
}

// Manifest represents one content-addressed scope snapshot.
type Manifest struct {
	Version    uint32
	Scope      ScopeKey
	Entries    map[string]Entry
	RootDigest digest.Digest
}

// ScopeHead points to the current materialized snapshot for one scope.
type ScopeHead struct {
	Scope         ScopeKey
	RootDigest    digest.Digest
	MaterialRefID string
	Generation    uint64
	ChainDepth    uint32
}
