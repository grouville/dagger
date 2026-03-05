package idtui

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"dagger.io/dagger"
	"github.com/dagger/dagger/util/patchpreview"
)

type changesetDiffStatEntry struct {
	Path         string `json:"path"`
	Kind         string `json:"kind"`
	AddedLines   int    `json:"addedLines"`
	RemovedLines int    `json:"removedLines"`
}

func PreviewPatch(ctx context.Context, dag *dagger.Client, changeset *dagger.Changeset) (*patchpreview.PatchPreview, error) {
	diffStat, err := loadChangesetDiffStat(ctx, dag, changeset)
	if err != nil {
		if !isDiffStatUnavailableError(err) {
			return nil, err
		}

		diffStat, err = loadChangesetPathSummary(ctx, changeset)
		if err != nil {
			return nil, err
		}
	}
	return patchpreview.New(toPatchPreviewEntries(diffStat)), nil
}

func loadChangesetDiffStat(ctx context.Context, dag *dagger.Client, changeset *dagger.Changeset) ([]changesetDiffStatEntry, error) {
	q := dag.QueryBuilder().
		Select("loadChangesetFromID").
		Arg("id", changeset).
		Select("diffStat")

	var diffStat []changesetDiffStatEntry
	if err := q.Bind(&diffStat).Execute(ctx); err != nil {
		return nil, fmt.Errorf("get diff stat: %w", err)
	}
	return diffStat, nil
}

func loadChangesetPathSummary(ctx context.Context, changeset *dagger.Changeset) ([]changesetDiffStatEntry, error) {
	addedPaths, err := changeset.AddedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("get added paths: %w", err)
	}
	modifiedPaths, err := changeset.ModifiedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("get modified paths: %w", err)
	}
	removedPaths, err := changeset.RemovedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("get removed paths: %w", err)
	}

	summary := make([]changesetDiffStatEntry, 0, len(addedPaths)+len(modifiedPaths)+len(removedPaths))
	for _, path := range addedPaths {
		summary = append(summary, changesetDiffStatEntry{
			Path: path,
			Kind: "ADDED",
		})
	}
	for _, path := range modifiedPaths {
		summary = append(summary, changesetDiffStatEntry{
			Path: path,
			Kind: "MODIFIED",
		})
	}
	for _, path := range removedPaths {
		summary = append(summary, changesetDiffStatEntry{
			Path: path,
			Kind: "REMOVED",
		})
	}

	return summary, nil
}

func isDiffStatUnavailableError(err error) bool {
	var extErr interface {
		error
		Extensions() map[string]any
	}
	if errors.As(err, &extErr) {
		code, _ := extErr.Extensions()["code"].(string)
		if code == "GRAPHQL_VALIDATION_FAILED" {
			return true
		}
	}

	// querybuilder can surface validation failures as plain wrapped HTTP errors
	// with escaped quotes, so match on stable fragments.
	msg := err.Error()
	return strings.Contains(msg, "Cannot query field") &&
		strings.Contains(msg, "diffStat") &&
		strings.Contains(msg, "Changeset")
}

func toPatchPreviewEntries(diffStat []changesetDiffStatEntry) []patchpreview.Entry {
	entries := make([]patchpreview.Entry, 0, len(diffStat))
	for _, entry := range diffStat {
		entries = append(entries, patchpreview.Entry{
			Path:    entry.Path,
			Kind:    entry.Kind,
			Added:   entry.AddedLines,
			Removed: entry.RemovedLines,
		})
	}
	return entries
}
