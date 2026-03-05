package cas

import (
	"errors"
	"fmt"
)

type MaterializeApplier interface {
	Delete(path string) error
	Upsert(path string, entry Entry) error
	Close() error
}

// ExecuteMaterializePlan applies deletes then upserts and always closes the applier.
func ExecuteMaterializePlan(applier MaterializeApplier, plan MaterializePlan) (rerr error) {
	defer func() {
		if err := applier.Close(); err != nil {
			rerr = errors.Join(rerr, fmt.Errorf("close applier: %w", err))
		}
	}()

	for _, path := range plan.Deletes {
		if err := applier.Delete(path); err != nil {
			return fmt.Errorf("delete %q: %w", path, err)
		}
	}
	for _, upsert := range plan.Upserts {
		if err := applier.Upsert(upsert.Path, upsert.Entry); err != nil {
			return fmt.Errorf("upsert %q: %w", upsert.Path, err)
		}
	}

	return nil
}
