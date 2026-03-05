package cas

import (
	"fmt"
	"strings"
)

type ManifestDelta struct {
	Upserts map[string]Entry
	Deletes map[string]struct{}
	None    map[string]struct{}
}

func (delta ManifestDelta) Validate() error {
	for path := range delta.Upserts {
		normalized, err := NormalizeEntryPath(path)
		if err != nil {
			return fmt.Errorf("normalize upsert path %q: %w", path, err)
		}
		if _, exists := delta.Deletes[normalized]; exists {
			return fmt.Errorf("path %q cannot be both upsert and delete", normalized)
		}
	}
	for path := range delta.Deletes {
		if _, err := NormalizeEntryPath(path); err != nil {
			return fmt.Errorf("normalize delete path %q: %w", path, err)
		}
	}
	for path := range delta.None {
		if _, err := NormalizeEntryPath(path); err != nil {
			return fmt.Errorf("normalize none path %q: %w", path, err)
		}
	}
	return nil
}

// ApplyDelta applies upsert/delete changes to a manifest and recomputes root digest.
func ApplyDelta(base Manifest, delta ManifestDelta) (Manifest, error) {
	if err := delta.Validate(); err != nil {
		return Manifest{}, err
	}

	out := Manifest{
		Version: base.Version,
		Scope:   base.Scope,
		Entries: make(map[string]Entry, len(base.Entries)),
	}
	for path, entry := range base.Entries {
		normalizedPath, err := NormalizeEntryPath(path)
		if err != nil {
			return Manifest{}, fmt.Errorf("normalize base path %q: %w", path, err)
		}
		entry.Path = normalizedPath
		out.Entries[normalizedPath] = entry
	}

	for rawDeletePath := range delta.Deletes {
		deletePath, err := NormalizeEntryPath(rawDeletePath)
		if err != nil {
			return Manifest{}, err
		}
		delete(out.Entries, deletePath)

		// Deleting a directory should prune any descendants.
		deletePrefix := deletePath + "/"
		for path := range out.Entries {
			if strings.HasPrefix(path, deletePrefix) {
				delete(out.Entries, path)
			}
		}
	}

	for rawUpsertPath, entry := range delta.Upserts {
		upsertPath, err := NormalizeEntryPath(rawUpsertPath)
		if err != nil {
			return Manifest{}, err
		}
		entry.Path = upsertPath
		out.Entries[upsertPath] = entry
	}

	rootDigest, err := RootDigest(out)
	if err != nil {
		return Manifest{}, err
	}
	out.RootDigest = rootDigest

	return out, nil
}
