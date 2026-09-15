package dagql

import (
	"context"
	"fmt"
	"slices"
	"strings"

	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/opencontainers/go-digest"
)

const contentUsagePrefix = "content/"

// Expand roots into physical blob identities outside egraphMu. Different
// versions of a tree can own the same file bytes; charging the whole tree to
// each root would overstate both disk usage and the benefit of pruning one.
func expandContentUsageInputs(ctx context.Context, manager bkcache.SnapshotManager, inputs []cacheUsageMeasurementInput) error {
	closures := make(map[digest.Digest][]bkcache.ContentUsage)
	for i := range inputs {
		input := &inputs[i]
		if len(input.contentLinks) == 0 {
			continue
		}
		cm, ok := manager.(bkcache.ContentManager)
		if !ok {
			return fmt.Errorf("cache storage does not support content-root accounting")
		}
		input.contentSizes = make(map[string]int64)
		for _, root := range input.contentLinks {
			objects, ok := closures[root.Digest]
			if !ok {
				var err error
				objects, err = cm.ContentUsage(ctx, root.Digest)
				if err != nil {
					return fmt.Errorf("measure content root %s: %w", root.Digest, err)
				}
				closures[root.Digest] = objects
			}
			for _, obj := range objects {
				input.contentSizes[contentUsagePrefix+obj.Digest.String()] = obj.Size
			}
		}
		for identity := range input.contentSizes {
			input.contentIdentities = append(input.contentIdentities, identity)
		}
		slices.Sort(input.contentIdentities)
		input.identities = append(input.identities, input.contentIdentities...)
		slices.Sort(input.identities)
		input.identities = slices.Compact(input.identities)
	}
	return nil
}

func isContentUsageIdentity(identity string) bool {
	return strings.HasPrefix(identity, contentUsagePrefix)
}

// Caller holds egraphMu. Do not publish a measured closure over newer owner
// links: an omitted shared owner would give incorrect last-owner GC credit.
func (c *Cache) publishContentUsageIdentitiesLocked(inputs []cacheUsageMeasurementInput) error {
	byResult := make(map[sharedResultID]cacheUsageMeasurementInput, len(inputs))
	for _, input := range inputs {
		byResult[input.resultID] = input
	}
	for id, res := range c.resultsByID {
		if res == nil {
			continue
		}
		current := res.loadPayloadState().contentOwnerLinks
		if !slices.Equal(current, byResult[id].contentLinks) {
			return fmt.Errorf("content ownership changed while measuring result %d; retry accounting", id)
		}
	}
	for id, res := range c.resultsByID {
		if res != nil {
			res.contentUsageIdentities = slices.Clone(byResult[id].contentIdentities)
		}
	}
	return nil
}
