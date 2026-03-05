package cas

import (
	"fmt"
	"sort"
	"strings"
)

type MaterializePlan struct {
	Deletes []string
	Upserts []MaterializeUpsert
}

type MaterializeUpsert struct {
	Path  string
	Entry Entry
}

// BuildMaterializePlan computes the minimal delete/upsert operations to move from previous to next.
func BuildMaterializePlan(previous, next Manifest) (MaterializePlan, error) {
	prevEntries, err := normalizeEntries(previous.Entries)
	if err != nil {
		return MaterializePlan{}, err
	}
	nextEntries, err := normalizeEntries(next.Entries)
	if err != nil {
		return MaterializePlan{}, err
	}

	plan := MaterializePlan{
		Deletes: []string{},
		Upserts: []MaterializeUpsert{},
	}

	for path := range prevEntries {
		if _, stillExists := nextEntries[path]; stillExists {
			continue
		}
		plan.Deletes = append(plan.Deletes, path)
	}

	for path, nextEntry := range nextEntries {
		prevEntry, existed := prevEntries[path]
		if !existed {
			plan.Upserts = append(plan.Upserts, MaterializeUpsert{Path: path, Entry: nextEntry})
			continue
		}
		changed, err := entryChanged(prevEntry, nextEntry)
		if err != nil {
			return MaterializePlan{}, fmt.Errorf("compare entry %q: %w", path, err)
		}
		if changed {
			plan.Upserts = append(plan.Upserts, MaterializeUpsert{Path: path, Entry: nextEntry})
		}
	}

	sort.Slice(plan.Upserts, func(i, j int) bool {
		return plan.Upserts[i].Path < plan.Upserts[j].Path
	})
	// Delete deeper paths first so directory deletes happen after child deletes.
	sort.Slice(plan.Deletes, func(i, j int) bool {
		di := strings.Count(plan.Deletes[i], "/")
		dj := strings.Count(plan.Deletes[j], "/")
		if di == dj {
			return plan.Deletes[i] < plan.Deletes[j]
		}
		return di > dj
	})

	return plan, nil
}

func normalizeEntries(entries map[string]Entry) (map[string]Entry, error) {
	out := make(map[string]Entry, len(entries))
	for rawPath, entry := range entries {
		path, err := NormalizeEntryPath(rawPath)
		if err != nil {
			return nil, fmt.Errorf("normalize path %q: %w", rawPath, err)
		}
		entry.Path = path
		out[path] = entry
	}
	return out, nil
}

func entryChanged(previous, next Entry) (bool, error) {
	prevDigest, err := EntryDigest(previous)
	if err != nil {
		return false, err
	}
	nextDigest, err := EntryDigest(next)
	if err != nil {
		return false, err
	}
	return prevDigest != nextDigest, nil
}
