// Package filetree defines the versioned storage format for immutable filesync
// trees. Its storage digests are not Dagger semantic content digests.
//
// Special files are unsupported: import adapters must fail closed or retain the
// existing import path, never silently omit unsupported entries. This package
// does not read filesystems, follow symlinks, or resolve hardlinks across trees.
package filetree

import (
	"bytes"
	"cmp"
	_ "crypto/sha256" // Register the storage format's required digest algorithm.
	"encoding/json"
	"fmt"
	"io"
	"slices"

	"github.com/opencontainers/go-digest"
)

const TreeVersion = 1

type Object struct {
	Digest digest.Digest `json:"digest"`
	Size   int64         `json:"size"`
}

func (o Object) Validate() error {
	if err := o.Digest.Validate(); err != nil {
		return fmt.Errorf("invalid object digest: %w", err)
	}
	if o.Digest.Algorithm() != digest.SHA256 {
		return fmt.Errorf("unsupported object digest algorithm %q", o.Digest.Algorithm())
	}
	if o.Size < 0 {
		return fmt.Errorf("negative object size %d", o.Size)
	}
	return nil
}

type Xattr struct {
	Name  []byte `json:"name"`
	Value []byte `json:"value"`
}

type Metadata struct {
	Mode    uint32  `json:"mode"` // POSIX permission/special bits only, not file type bits.
	UID     uint32  `json:"uid"`
	GID     uint32  `json:"gid"`
	ModTime int64   `json:"modTime"` // Nanoseconds since the Unix epoch.
	Xattrs  []Xattr `json:"xattrs,omitempty"`
}

type Kind string

const (
	File      Kind = "file"
	Directory Kind = "directory"
	Symlink   Kind = "symlink"
	Hardlink  Kind = "hardlink"
)

type Entry struct {
	Name     []byte    `json:"name"`
	Kind     Kind      `json:"kind"`
	Metadata *Metadata `json:"metadata,omitempty"`
	Object   *Object   `json:"object,omitempty"`
	Linkname []byte    `json:"linkname,omitempty"`
}

type Tree struct {
	Version  int      `json:"version"`
	Metadata Metadata `json:"metadata"`
	Entries  []Entry  `json:"entries"`
}

// Encode validates and returns canonical JSON. Entries and xattrs are sorted by
// raw name bytes without modifying the caller's tree. Byte strings are base64
// encoded by JSON, preserving non-UTF-8 filenames, link targets and xattr names.
func Encode(tree Tree) ([]byte, error) {
	if tree.Version != TreeVersion {
		return nil, fmt.Errorf("unsupported tree version %d", tree.Version)
	}
	metadata, err := canonicalMetadata(tree.Metadata)
	if err != nil {
		return nil, fmt.Errorf("root metadata: %w", err)
	}
	tree.Metadata = metadata
	entries := make([]Entry, len(tree.Entries))
	seenObjects := make(map[digest.Digest]int64)
	for i, entry := range tree.Entries {
		if !validName(entry.Name) {
			return nil, fmt.Errorf("invalid entry name %q", entry.Name)
		}
		if err := validateEntry(entry); err != nil {
			return nil, fmt.Errorf("entry %q: %w", entry.Name, err)
		}
		entry.Name = bytes.Clone(entry.Name)
		entry.Linkname = bytes.Clone(entry.Linkname)
		if entry.Metadata != nil {
			metadata, err := canonicalMetadata(*entry.Metadata)
			if err != nil {
				return nil, fmt.Errorf("entry %q metadata: %w", entry.Name, err)
			}
			entry.Metadata = &metadata
		}
		if entry.Object != nil {
			object := *entry.Object
			if err := object.Validate(); err != nil {
				return nil, fmt.Errorf("entry %q: %w", entry.Name, err)
			}
			if size, exists := seenObjects[object.Digest]; exists && size != object.Size {
				return nil, fmt.Errorf("conflicting sizes for object %s", object.Digest)
			}
			seenObjects[object.Digest] = object.Size
			entry.Object = &object
		}
		entries[i] = entry
	}
	slices.SortFunc(entries, func(a, b Entry) int { return bytes.Compare(a.Name, b.Name) })
	for i := 1; i < len(entries); i++ {
		if bytes.Equal(entries[i-1].Name, entries[i].Name) {
			return nil, fmt.Errorf("duplicate entry name %q", entries[i].Name)
		}
	}
	tree.Entries = entries
	return json.Marshal(tree)
}

// Decode accepts only the canonical representation. Re-encoding rejects JSON
// duplicates, alternate field/entry ordering, insignificant whitespace and
// omitted required fields as well as values rejected by Encode.
func Decode(data []byte) (Tree, error) {
	var tree Tree
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&tree); err != nil {
		return Tree{}, fmt.Errorf("decode tree: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return Tree{}, fmt.Errorf("trailing data after tree")
	}
	canonical, err := Encode(tree)
	if err != nil {
		return Tree{}, err
	}
	if !bytes.Equal(data, canonical) {
		return Tree{}, fmt.Errorf("noncanonical tree encoding")
	}
	return tree, nil
}

// References returns the unique direct child objects sorted by digest, not the
// transitive closure. Call only on trees validated by Encode or Decode; those
// functions reject conflicting sizes for the same digest within a tree.
func (tree Tree) References() []Object {
	objects := make(map[digest.Digest]Object)
	for _, entry := range tree.Entries {
		if entry.Object != nil {
			objects[entry.Object.Digest] = *entry.Object
		}
	}
	refs := make([]Object, 0, len(objects))
	for _, object := range objects {
		refs = append(refs, object)
	}
	slices.SortFunc(refs, func(a, b Object) int { return cmp.Compare(a.Digest, b.Digest) })
	return refs
}

func canonicalMetadata(metadata Metadata) (Metadata, error) {
	if metadata.Mode & ^uint32(0o7777) != 0 {
		return Metadata{}, fmt.Errorf("unsupported mode bits %#o", metadata.Mode)
	}
	xattrs := make([]Xattr, len(metadata.Xattrs))
	for i, xattr := range metadata.Xattrs {
		if len(xattr.Name) == 0 || bytes.IndexByte(xattr.Name, 0) >= 0 {
			return Metadata{}, fmt.Errorf("invalid xattr name %q", xattr.Name)
		}
		// Empty and nil xattr values both represent the same empty byte string.
		value := append([]byte{}, xattr.Value...)
		xattrs[i] = Xattr{Name: bytes.Clone(xattr.Name), Value: value}
	}
	slices.SortFunc(xattrs, func(a, b Xattr) int { return bytes.Compare(a.Name, b.Name) })
	for i := 1; i < len(xattrs); i++ {
		if bytes.Equal(xattrs[i-1].Name, xattrs[i].Name) {
			return Metadata{}, fmt.Errorf("duplicate xattr name %q", xattrs[i].Name)
		}
	}
	metadata.Xattrs = xattrs
	return metadata, nil
}

func validateEntry(entry Entry) error {
	switch entry.Kind {
	case File:
		if entry.Metadata == nil || entry.Object == nil || len(entry.Linkname) != 0 {
			return fmt.Errorf("file requires metadata and object only")
		}
	case Directory:
		if entry.Metadata != nil || entry.Object == nil || len(entry.Linkname) != 0 {
			return fmt.Errorf("directory requires child tree object only")
		}
	case Symlink:
		if entry.Metadata == nil || entry.Object != nil || len(entry.Linkname) == 0 || bytes.IndexByte(entry.Linkname, 0) >= 0 {
			return fmt.Errorf("symlink requires metadata and nonempty NUL-free target only")
		}
	case Hardlink:
		if entry.Metadata != nil || entry.Object != nil || !validHardlink(entry.Linkname) {
			return fmt.Errorf("hardlink requires clean root-relative target only")
		}
	default:
		return fmt.Errorf("unsupported entry kind %q", entry.Kind)
	}
	return nil
}

func validName(name []byte) bool {
	return len(name) != 0 && !bytes.Equal(name, []byte(".")) && !bytes.Equal(name, []byte("..")) &&
		bytes.IndexByte(name, '/') < 0 && bytes.IndexByte(name, 0) < 0
}

func validHardlink(target []byte) bool {
	// Paths in the format use '/' regardless of the importing host platform.
	for _, component := range bytes.Split(target, []byte("/")) {
		if !validName(component) {
			return false
		}
	}
	return true
}
