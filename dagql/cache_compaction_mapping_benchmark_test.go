package dagql

import (
	"context"
	"errors"
	"fmt"
	"io"
	"testing"
	"time"
)

// Populate real persisted scalar results and dependency edges through the
// existing fixture helper. Only compaction is timed; no GC is forced.
func BenchmarkPopulatedCacheCompaction(b *testing.B) {
	for _, fixture := range []benchmarkMetadataFixture{benchmarkMetadataMinimal, benchmarkMetadataShared} {
		b.Run(string(fixture), func(b *testing.B) {
			b.ReportAllocs()
			var hold time.Duration
			for range b.N {
				b.StopTimer()
				c, ctx, _ := benchmarkMetadataPruneCache(b, 50_000, fixture, "", io.Discard)
				var sample *ResultCall
				c.egraphMu.Lock()
				for _, result := range c.resultsByID {
					frame := result.loadResultCall()
					if frame != nil && (fixture == benchmarkMetadataMinimal || frame.Field == "shared") {
						sample = frame.clone()
						break
					}
				}
				for i := range 5_000 {
					c.ensureEqClassForDigestLocked(ctx, fmt.Sprintf("unused-mapping-%d", i))
				}
				before := c.cacheMetadataEstimateLocked()
				beforeErr := cacheDerivedIndexesErrorLocked(c)
				c.egraphMu.Unlock()
				if beforeErr != nil || sample == nil {
					b.Fatalf("invalid populated fixture: sample=%v, indexes=%v", sample, beforeErr)
				}
				b.StartTimer()
				c.egraphMu.Lock()
				started := time.Now()
				changed, oldSlots, newSlots := c.compactEqClassesLocked(true)
				c.egraphMu.Unlock()
				hold += time.Since(started)
				b.StopTimer()
				c.egraphMu.Lock()
				after := c.cacheMetadataEstimateLocked()
				afterErr := cacheDerivedIndexesErrorLocked(c)
				c.egraphMu.Unlock()
				if !changed || oldSlots <= newSlots || before.ResultCount != after.ResultCount || before.TermCount != after.TermCount || afterErr != nil {
					b.Fatalf("compaction changed live contents: changed=%v, slots=%d→%d, counts=%+v→%+v, indexes=%v", changed, oldSlots, newSlots, before, after, afterErr)
				}
				hit, err := c.GetOrInitCall(ctx, "mapping-verification", noopTypeResolver{}, &CallRequest{ResultCall: sample}, func(context.Context) (AnyResult, error) {
					return nil, errors.New("the populated result should remain cached")
				})
				if err != nil || !hit.HitCache() {
					b.Fatalf("populated result did not remain cached: %v", err)
				}
				b.ReportMetric(float64(before.ResultCount), "results")
				b.ReportMetric(float64(before.TermCount), "terms")
				b.ReportMetric(float64(oldSlots), "old-class-slots")
				b.ReportMetric(float64(newSlots), "new-class-slots")
				if err := c.CloseDiscardingPersistence(); err != nil {
					b.Fatal(err)
				}
			}
			b.ReportMetric(float64(hold.Nanoseconds())/float64(b.N), "write-lock-hold-ns")
		})
	}
}
