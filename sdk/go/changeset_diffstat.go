package dagger

import "context"

type ChangesetDiffKind string

const (
	ChangesetDiffKindAdded    ChangesetDiffKind = "ADDED"
	ChangesetDiffKindModified ChangesetDiffKind = "MODIFIED"
	ChangesetDiffKindRemoved  ChangesetDiffKind = "REMOVED"
)

type ChangesetDiffStatEntry struct {
	Path         string            `json:"path"`
	Kind         ChangesetDiffKind `json:"kind"`
	AddedLines   int               `json:"addedLines"`
	RemovedLines int               `json:"removedLines"`
}

func (r *Changeset) DiffStat(ctx context.Context) ([]ChangesetDiffStatEntry, error) {
	q := r.query.Select("diffStat")

	var response []ChangesetDiffStatEntry

	q = q.Bind(&response)
	return response, q.Execute(ctx)
}
