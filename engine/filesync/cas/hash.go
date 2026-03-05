package cas

import (
	"encoding/json"
	"fmt"
	"path"
	"sort"
	"strings"

	digest "github.com/opencontainers/go-digest"
)

type entryDigestPayload struct {
	Kind       EntryKind         `json:"kind"`
	Mode       uint32            `json:"mode,omitempty"`
	UID        uint32            `json:"uid,omitempty"`
	GID        uint32            `json:"gid,omitempty"`
	Size       int64             `json:"size,omitempty"`
	LinkTarget string            `json:"linkTarget,omitempty"`
	BlobDigest string            `json:"blobDigest,omitempty"`
	XAttrs     []xattrDigestPair `json:"xattrs,omitempty"`
}

type xattrDigestPair struct {
	Key   string `json:"key"`
	Value []byte `json:"value"`
}

type nodeDigestPayload struct {
	DirEntryDigest string            `json:"dirEntryDigest,omitempty"`
	Children       []nodeDigestChild `json:"children"`
}

type nodeDigestChild struct {
	Name          string `json:"name"`
	Type          string `json:"type"`
	EntryDigest   string `json:"entryDigest,omitempty"`
	SubtreeDigest string `json:"subtreeDigest,omitempty"`
}

type treeNode struct {
	children map[string]string // child name -> full child path
}

// EntryDigest returns a deterministic digest for one manifest entry.
func EntryDigest(entry Entry) (digest.Digest, error) {
	payload, err := entryDigestInput(entry)
	if err != nil {
		return "", err
	}
	data, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("marshal entry digest payload: %w", err)
	}
	return digest.FromBytes(data), nil
}

// RootDigest returns a deterministic root digest for the full manifest tree.
func RootDigest(manifest Manifest) (digest.Digest, error) {
	normalizedEntries, nodes, err := buildDigestTree(manifest.Entries)
	if err != nil {
		return "", err
	}

	return digestNode("", normalizedEntries, nodes)
}

func buildDigestTree(entries map[string]Entry) (map[string]Entry, map[string]*treeNode, error) {
	normalizedEntries := make(map[string]Entry, len(entries))
	nodes := map[string]*treeNode{
		"": {children: map[string]string{}},
	}

	ensureNode := func(dir string) *treeNode {
		node, ok := nodes[dir]
		if !ok {
			node = &treeNode{children: map[string]string{}}
			nodes[dir] = node
		}
		return node
	}

	for rawPath, entry := range entries {
		entryPath, err := NormalizeEntryPath(rawPath)
		if err != nil {
			return nil, nil, fmt.Errorf("normalize entry path %q: %w", rawPath, err)
		}
		if entry.Path != "" {
			normalizedEntryPath, err := NormalizeEntryPath(entry.Path)
			if err != nil {
				return nil, nil, fmt.Errorf("normalize entry.Path %q: %w", entry.Path, err)
			}
			if normalizedEntryPath != entryPath {
				return nil, nil, fmt.Errorf("entry path mismatch for %q: map key %q", entry.Path, rawPath)
			}
		}
		entry.Path = entryPath
		normalizedEntries[entryPath] = entry

		parts := strings.Split(entryPath, "/")
		curDir := ""
		for i, part := range parts {
			if part == "" {
				return nil, nil, fmt.Errorf("invalid empty path part in %q", entryPath)
			}

			parent := ensureNode(curDir)
			nextPath := part
			if curDir != "" {
				nextPath = path.Join(curDir, part)
			}
			if prev, exists := parent.children[part]; exists && prev != nextPath {
				return nil, nil, fmt.Errorf("conflicting child mapping for %q under %q", part, curDir)
			}
			parent.children[part] = nextPath

			isLast := i == len(parts)-1
			if isLast {
				if entry.Kind == EntryDir {
					ensureNode(nextPath)
				}
				break
			}

			curDir = nextPath
			ensureNode(curDir)
		}
	}

	return normalizedEntries, nodes, nil
}

func digestNode(
	dirPath string,
	entries map[string]Entry,
	nodes map[string]*treeNode,
) (digest.Digest, error) {
	node, ok := nodes[dirPath]
	if !ok {
		return "", fmt.Errorf("missing tree node for %q", dirPath)
	}

	payload := nodeDigestPayload{
		Children: make([]nodeDigestChild, 0, len(node.children)),
	}
	if dirPath != "" {
		if dirEntry, ok := entries[dirPath]; ok {
			if dirEntry.Kind != EntryDir {
				return "", fmt.Errorf("non-directory entry %q cannot have children", dirPath)
			}
			dgst, err := EntryDigest(dirEntry)
			if err != nil {
				return "", err
			}
			payload.DirEntryDigest = dgst.String()
		}
	}

	names := make([]string, 0, len(node.children))
	for name := range node.children {
		names = append(names, name)
	}
	sort.Strings(names)

	for _, name := range names {
		childPath := node.children[name]
		childNode, hasChildNode := nodes[childPath]
		entry, hasEntry := entries[childPath]

		if hasChildNode && (!hasEntry || entry.Kind == EntryDir) {
			subtreeDigest, err := digestNode(childPath, entries, nodes)
			if err != nil {
				return "", err
			}

			child := nodeDigestChild{
				Name:          name,
				Type:          "dir",
				SubtreeDigest: subtreeDigest.String(),
			}
			if hasEntry {
				dgst, err := EntryDigest(entry)
				if err != nil {
					return "", err
				}
				child.EntryDigest = dgst.String()
			}
			payload.Children = append(payload.Children, child)
			continue
		}

		if !hasEntry {
			_ = childNode
			return "", fmt.Errorf("missing leaf entry for %q", childPath)
		}
		if entry.Kind == EntryDir {
			return "", fmt.Errorf("directory entry %q is missing subtree", childPath)
		}

		entryDigest, err := EntryDigest(entry)
		if err != nil {
			return "", err
		}
		payload.Children = append(payload.Children, nodeDigestChild{
			Name:        name,
			Type:        "leaf",
			EntryDigest: entryDigest.String(),
		})
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("marshal node digest payload: %w", err)
	}
	return digest.FromBytes(data), nil
}

func entryDigestInput(entry Entry) (entryDigestPayload, error) {
	payload := entryDigestPayload{
		Kind:       entry.Kind,
		Mode:       entry.Mode,
		UID:        entry.UID,
		GID:        entry.GID,
		Size:       entry.Size,
		LinkTarget: entry.LinkTarget,
		XAttrs:     []xattrDigestPair{},
	}

	if entry.BlobDigest != "" {
		if err := entry.BlobDigest.Validate(); err != nil {
			return entryDigestPayload{}, fmt.Errorf("invalid blob digest: %w", err)
		}
		payload.BlobDigest = entry.BlobDigest.String()
	}

	if len(entry.XAttrs) > 0 {
		keys := make([]string, 0, len(entry.XAttrs))
		for key := range entry.XAttrs {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			payload.XAttrs = append(payload.XAttrs, xattrDigestPair{
				Key:   key,
				Value: append([]byte(nil), entry.XAttrs[key]...),
			})
		}
	}

	if len(payload.XAttrs) == 0 {
		payload.XAttrs = nil
	}

	return payload, nil
}
