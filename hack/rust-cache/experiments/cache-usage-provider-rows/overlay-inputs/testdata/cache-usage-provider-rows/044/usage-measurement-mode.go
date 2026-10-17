package dagql

import (
	"context"
	"os"
	"runtime"
	"strconv"
	"sync/atomic"
	"time"
)

// Diagnostic-only switch. The upstream patch has no mode, endpoint or counters.
var lazyUsageMapsDiagnostic atomic.Bool

func init() {
	enabled, _ := strconv.ParseBool(os.Getenv("DAGGER_DIAG_LAZY_USAGE_MAPS"))
	lazyUsageMapsDiagnostic.Store(enabled)
}

// MeasureUsageDiagnostic prepares the existing prune state without planning
// or executing any eviction. The caller serializes it with actual GC.
func (c *Cache) MeasureUsageDiagnostic(ctx context.Context, enabled bool) (map[string]any, error) {
	previous := lazyUsageMapsDiagnostic.Swap(enabled)
	defer lazyUsageMapsDiagnostic.Store(previous)
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	start := time.Now()
	_, snapshot, complete, err := c.measurePruneState(ctx, 0, CachePrunePolicy{All: true})
	elapsed := time.Since(start)
	runtime.ReadMemStats(&after)
	return map[string]any{
		"enabled": enabled, "complete": complete, "rows": len(snapshot.results),
		"used_bytes": snapshot.usedBytes, "seconds": elapsed.Seconds(),
		"allocated_bytes": after.TotalAlloc - before.TotalAlloc,
		"allocations":     after.Mallocs - before.Mallocs,
		"go_gc_cycles":    after.NumGC - before.NumGC,
	}, err
}
