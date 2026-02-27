package idtui

import (
	"context"
	"fmt"

	"dagger.io/dagger"
	"github.com/dagger/dagger/util/patchpreview"
)

func PreviewPatch(ctx context.Context, changeset *dagger.Changeset) (*patchpreview.PatchPreview, error) {
	rawPatch, err := changeset.AsPatch().Contents(ctx)
	if err != nil {
		preview, fallbackErr := patchpreview.NewFromChangesetPaths(ctx, changeset)
		if fallbackErr == nil {
			return preview, nil
		}
		return nil, fmt.Errorf("get patch: %w", err)
	}
	return patchpreview.New(ctx, rawPatch, changeset)
}
