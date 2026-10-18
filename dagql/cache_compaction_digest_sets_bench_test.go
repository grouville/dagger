package dagql

import (
	"fmt"
	"io"
	"testing"
	"time"
)

// The listing profile has hundreds of thousands of live classes. Keep that
// live set substantial; a million mostly dead slots exercises another cost.
func BenchmarkCompactLiveDigestSets(b *testing.B) {
	for _, live := range []int{16384, 131072} {
		b.Run(fmt.Sprint(live), func(b *testing.B) {
			b.ReportAllocs()
			var held time.Duration
			for range b.N {
				b.StopTimer()
				ctx := benchmarkMetadataContext(b, io.Discard)
				c, err := NewCache(ctx, "", nil, nil)
				if err != nil {
					b.Fatal(err)
				}
				benchmarkMetadataPopulateUnpruneableFloor(b, c, ctx, live)
				c.egraphMu.Lock()
				for i := range live / 4 {
					c.ensureEqClassForDigestLocked(ctx, fmt.Sprintf("dead-compaction-%d", i))
				}
				c.egraphMu.Unlock()
				b.StartTimer()
				c.egraphMu.Lock()
				start := time.Now()
				changed, oldSlots, newSlots := c.compactEqClassesLocked(true)
				held += time.Since(start)
				c.egraphMu.Unlock()
				b.StopTimer()
				if !changed || oldSlots <= newSlots || newSlots != live {
					b.Fatalf("unexpected class count: changed=%v old=%d new=%d live=%d", changed, oldSlots, newSlots, live)
				}
				c.egraphMu.Lock()
				err = cacheDerivedIndexesErrorLocked(c)
				c.egraphMu.Unlock()
				if err != nil {
					b.Fatal(err)
				}
				if err := c.Close(ctx); err != nil {
					b.Fatal(err)
				}
			}
			b.ReportMetric(float64(held.Nanoseconds())/float64(b.N), "write-lock-ns/op")
		})
	}
}
