package idtui

import (
	"context"
	"fmt"

	"dagger.io/dagger"
	"github.com/dagger/dagger/util/patchpreview"
)

func PreviewPatch(ctx context.Context, changeset *dagger.Changeset) (*patchpreview.PatchPreview, error) {
	diffStat, err := changeset.DiffStat(ctx)
	if err != nil {
		return nil, fmt.Errorf("get diff stat: %w", err)
	}

	entries := make([]patchpreview.Entry, 0, len(diffStat))
	for _, entry := range diffStat {
		entries = append(entries, patchpreview.Entry{
			Path:    entry.Path,
			Kind:    string(entry.Kind),
			Added:   entry.AddedLines,
			Removed: entry.RemovedLines,
		})
	}

	return patchpreview.New(entries), nil
}
