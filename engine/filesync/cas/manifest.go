package cas

import (
	"encoding/json"
	"fmt"
	"sort"

	digest "github.com/opencontainers/go-digest"
)

type manifestRecord struct {
	Version    uint32                `json:"version"`
	Scope      string                `json:"scope"`
	RootDigest string                `json:"rootDigest,omitempty"`
	Entries    []manifestRecordEntry `json:"entries"`
}

type manifestRecordEntry struct {
	Path       string                `json:"path"`
	Kind       EntryKind             `json:"kind"`
	Mode       uint32                `json:"mode,omitempty"`
	UID        uint32                `json:"uid,omitempty"`
	GID        uint32                `json:"gid,omitempty"`
	Size       int64                 `json:"size,omitempty"`
	LinkTarget string                `json:"linkTarget,omitempty"`
	BlobDigest string                `json:"blobDigest,omitempty"`
	XAttrs     []manifestRecordXAttr `json:"xattrs,omitempty"`
}

type manifestRecordXAttr struct {
	Key   string `json:"key"`
	Value []byte `json:"value"`
}

// CanonicalBytes returns deterministic serialized bytes for the manifest.
func (m Manifest) CanonicalBytes() ([]byte, error) {
	record, err := m.toRecord()
	if err != nil {
		return nil, err
	}
	return json.Marshal(record)
}

// ParseManifest parses persisted manifest bytes into the in-memory shape.
func ParseManifest(payload []byte) (Manifest, error) {
	var record manifestRecord
	if err := json.Unmarshal(payload, &record); err != nil {
		return Manifest{}, fmt.Errorf("unmarshal manifest: %w", err)
	}
	return manifestFromRecord(record)
}

func (m Manifest) toRecord() (manifestRecord, error) {
	version := m.Version
	if version == 0 {
		version = ManifestVersion
	}
	if version != ManifestVersion {
		return manifestRecord{}, fmt.Errorf("unsupported manifest version: %d", version)
	}

	record := manifestRecord{
		Version: version,
		Scope:   m.Scope.String(),
		Entries: []manifestRecordEntry{},
	}
	if m.RootDigest != "" {
		if err := m.RootDigest.Validate(); err != nil {
			return manifestRecord{}, fmt.Errorf("invalid root digest: %w", err)
		}
		record.RootDigest = m.RootDigest.String()
	}

	paths := make([]string, 0, len(m.Entries))
	for path := range m.Entries {
		paths = append(paths, path)
	}
	sort.Strings(paths)

	for _, path := range paths {
		entry := m.Entries[path]
		recordEntry, err := entryToRecord(path, entry)
		if err != nil {
			return manifestRecord{}, err
		}
		record.Entries = append(record.Entries, recordEntry)
	}

	return record, nil
}

func entryToRecord(mapPath string, entry Entry) (manifestRecordEntry, error) {
	normalizedPath, err := NormalizeEntryPath(mapPath)
	if err != nil {
		return manifestRecordEntry{}, fmt.Errorf("normalize entry path %q: %w", mapPath, err)
	}
	if entry.Path != "" {
		entryPath, err := NormalizeEntryPath(entry.Path)
		if err != nil {
			return manifestRecordEntry{}, fmt.Errorf("normalize entry.Path %q: %w", entry.Path, err)
		}
		if entryPath != normalizedPath {
			return manifestRecordEntry{}, fmt.Errorf("entry path mismatch for %q: map key %q", entry.Path, mapPath)
		}
	}

	record := manifestRecordEntry{
		Path:       normalizedPath,
		Kind:       entry.Kind,
		Mode:       entry.Mode,
		UID:        entry.UID,
		GID:        entry.GID,
		Size:       entry.Size,
		LinkTarget: entry.LinkTarget,
		XAttrs:     []manifestRecordXAttr{},
	}

	if entry.BlobDigest != "" {
		if err := entry.BlobDigest.Validate(); err != nil {
			return manifestRecordEntry{}, fmt.Errorf("invalid blob digest for %q: %w", mapPath, err)
		}
		record.BlobDigest = entry.BlobDigest.String()
	}

	if len(entry.XAttrs) > 0 {
		keys := make([]string, 0, len(entry.XAttrs))
		for key := range entry.XAttrs {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			record.XAttrs = append(record.XAttrs, manifestRecordXAttr{
				Key:   key,
				Value: append([]byte(nil), entry.XAttrs[key]...),
			})
		}
	}

	return record, nil
}

func manifestFromRecord(record manifestRecord) (Manifest, error) {
	if record.Version == 0 {
		record.Version = ManifestVersion
	}
	if record.Version != ManifestVersion {
		return Manifest{}, fmt.Errorf("unsupported manifest version: %d", record.Version)
	}

	out := Manifest{
		Version: record.Version,
		Scope:   ScopeKey(record.Scope),
		Entries: map[string]Entry{},
	}

	if record.RootDigest != "" {
		dgst := digest.Digest(record.RootDigest)
		if err := dgst.Validate(); err != nil {
			return Manifest{}, fmt.Errorf("invalid root digest: %w", err)
		}
		out.RootDigest = dgst
	}

	for _, recordEntry := range record.Entries {
		path, err := NormalizeEntryPath(recordEntry.Path)
		if err != nil {
			return Manifest{}, fmt.Errorf("normalize entry path %q: %w", recordEntry.Path, err)
		}
		if _, exists := out.Entries[path]; exists {
			return Manifest{}, fmt.Errorf("duplicate entry path: %q", path)
		}

		entry := Entry{
			Path:       path,
			Kind:       recordEntry.Kind,
			Mode:       recordEntry.Mode,
			UID:        recordEntry.UID,
			GID:        recordEntry.GID,
			Size:       recordEntry.Size,
			LinkTarget: recordEntry.LinkTarget,
			XAttrs:     map[string][]byte{},
		}

		if recordEntry.BlobDigest != "" {
			dgst := digest.Digest(recordEntry.BlobDigest)
			if err := dgst.Validate(); err != nil {
				return Manifest{}, fmt.Errorf("invalid blob digest for %q: %w", path, err)
			}
			entry.BlobDigest = dgst
		}

		for _, xattr := range recordEntry.XAttrs {
			if xattr.Key == "" {
				return Manifest{}, fmt.Errorf("empty xattr key for %q", path)
			}
			if _, dup := entry.XAttrs[xattr.Key]; dup {
				return Manifest{}, fmt.Errorf("duplicate xattr key %q for %q", xattr.Key, path)
			}
			entry.XAttrs[xattr.Key] = append([]byte(nil), xattr.Value...)
		}
		if len(entry.XAttrs) == 0 {
			entry.XAttrs = nil
		}

		out.Entries[path] = entry
	}

	return out, nil
}
