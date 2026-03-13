package idtui

import (
	"context"
	"fmt"

	"dagger.io/dagger"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/util/patchpreview"
)

func PreviewPatch(ctx context.Context, dag *dagger.Client, changeset *dagger.Changeset) (*patchpreview.PatchPreview, error) {
	q := dag.QueryBuilder().
		Select("loadChangesetFromID").
		Arg("id", changeset).
		Select("diffStat")

	var diffStat []struct {
		Path         string `json:"path"`
		Kind         string `json:"kind"`
		AddedLines   int    `json:"addedLines"`
		RemovedLines int    `json:"removedLines"`
	}
	err := q.Bind(&diffStat).Execute(ctx)
	if err == nil {
		entries := make([]patchpreview.Entry, 0, len(diffStat))
		for _, stat := range diffStat {
			entries = append(entries, patchpreview.Entry{
				Path:    stat.Path,
				Kind:    stat.Kind,
				Added:   stat.AddedLines,
				Removed: stat.RemovedLines,
			})
		}
		return patchpreview.New(entries), nil
	}
	if !dagql.IsUnavailableFieldError(err, "Changeset", "diffStat") {
		return nil, fmt.Errorf("query diff stat: %w", err)
	}

	addedPaths, err := changeset.AddedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("fallback added paths: %w", err)
	}
	modifiedPaths, err := changeset.ModifiedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("fallback modified paths: %w", err)
	}
	removedPaths, err := changeset.RemovedPaths(ctx)
	if err != nil {
		return nil, fmt.Errorf("fallback removed paths: %w", err)
	}

	entries := make([]patchpreview.Entry, 0, len(addedPaths)+len(modifiedPaths)+len(removedPaths))
	for _, path := range addedPaths {
		entries = append(entries, patchpreview.Entry{
			Path: path,
			Kind: "ADDED",
		})
	}
	for _, path := range modifiedPaths {
		entries = append(entries, patchpreview.Entry{
			Path: path,
			Kind: "MODIFIED",
		})
	}
	for _, path := range removedPaths {
		entries = append(entries, patchpreview.Entry{
			Path: path,
			Kind: "REMOVED",
		})
	}
	return patchpreview.New(entries), nil
}
