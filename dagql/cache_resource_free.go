package dagql

import (
	"context"
	"fmt"
)

// ResultHasSessionResources is used only by the experimental snapshot
// checkpoint boundary. Values needing caller-owned resources are not eligible.
func (c *Cache) ResultHasSessionResources(ctx context.Context, result AnyResult) (bool, error) {
	if err := ctx.Err(); err != nil {
		return false, err
	}
	if result == nil || result.cacheSharedResult() == nil {
		return false, fmt.Errorf("check snapshot resources: missing result")
	}
	row := result.cacheSharedResult()
	c.egraphMu.RLock()
	defer c.egraphMu.RUnlock()
	if row.id == 0 || c.resultsByID[row.id] != row {
		return false, fmt.Errorf("check snapshot resources: result is not registered")
	}
	return row.requiredSessionResources != nil && row.requiredSessionResources.Size() != 0, nil
}
