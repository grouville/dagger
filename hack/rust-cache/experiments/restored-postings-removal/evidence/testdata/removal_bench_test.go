package dagql

import (
	"fmt"
	"testing"
)

func restoredPostingRemovalFixture(n int, restore bool) *Cache {
	c := &Cache{}
	c.egraphMu.Lock()
	defer c.egraphMu.Unlock()
	c.initEgraphLocked()
	c.egraphParents = []eqClassID{0, 1}
	digests := make(map[string]struct{}, n)
	results := make(map[sharedResultID]struct{}, n)
	for i := range n {
		digests[fmt.Sprintf("digest-%08x", i)] = struct{}{}
		id := sharedResultID(i + 1)
		results[id] = struct{}{}
		c.putResultLocked(&sharedResult{id: id})
	}
	c.eqClassToDigests[1] = digests
	c.outputEqClassResults[1] = results
	if restore {
		c.restoreDigestPostingsLocked()
	}
	return c
}

func BenchmarkRestoredDigestPostingRemoval(b *testing.B) {
	for _, n := range []int{128, 512, 2048, 4096} {
		b.Run(fmt.Sprint(n), func(b *testing.B) {
			b.ReportAllocs()
			outputs := map[eqClassID]struct{}{1: {}}
			for range b.N {
				b.StopTimer()
				c := restoredPostingRemovalFixture(n, true)
				c.egraphMu.Lock()
				b.StartTimer()
				for id := sharedResultID(1); id <= sharedResultID(n); id++ {
					c.removeResultDigestsLocked(id, outputs)
				}
				b.StopTimer()
				c.egraphMu.Unlock()
				if len(c.egraphResultsByDigest) != 0 || len(c.broadlyIndexedResults) != 0 {
					b.Fatal("removed results left stale digest postings")
				}
			}
		})
	}
}

func BenchmarkRestoredDigestPostingConstruction(b *testing.B) {
	for _, shape := range []string{"wide", "singleton"} {
		b.Run(shape, func(b *testing.B) {
			for _, n := range []int{128, 512, 2048, 4096} {
				b.Run(fmt.Sprint(n), func(b *testing.B) {
					b.ReportAllocs()
					for range b.N {
						b.StopTimer()
						c := restoredPostingRemovalFixture(n, false)
						if shape == "singleton" {
							delete(c.eqClassToDigests, 1)
							delete(c.outputEqClassResults, 1)
							c.egraphParents = make([]eqClassID, n+1)
							for i := range n {
								id := sharedResultID(i + 1)
								class := eqClassID(i + 1)
								c.egraphParents[class] = class
								c.eqClassToDigests[class] = map[string]struct{}{fmt.Sprintf("digest-%08x", i): {}}
								c.outputEqClassResults[class] = map[sharedResultID]struct{}{id: {}}
							}
						}
						c.egraphMu.Lock()
						b.StartTimer()
						c.restoreDigestPostingsLocked()
						b.StopTimer()
						c.egraphMu.Unlock()
						if len(c.egraphResultsByDigest) != n {
							b.Fatal("restored posting count changed")
						}
					}
				})
			}
		})
	}
}

// Exercise normal persisted-root selection and the ownership cascade, including
// an import, rather than measuring only the digest index helper.
func BenchmarkMetadataPruneRestoredWideOutput(b *testing.B) {
	for _, width := range []int{256, 1024, 4096} {
		b.Run(fmt.Sprint(width), func(b *testing.B) {
			b.ReportAllocs()
			for range b.N {
				b.StopTimer()
				f := cacheDerivedIndexWideOutputFixture(b, width, true)
				before := len(f.cache.resultsByID)
				maximum := cacheMetadataResultEstimatedBytes * int64(before) / 2
				b.StartTimer()
				report, err := f.cache.PruneMetadataEstimate(f.ctx, maximum, 1)
				b.StopTimer()
				if err != nil {
					b.Fatal(err)
				}
				b.ReportMetric(float64(report.RemovedPersistedRootCount), "roots/op")
				if !report.Triggered || report.AfterPrune.EstimatedBytes >= maximum || report.RemovedPersistedRootCount != before-len(f.cache.resultsByID) {
					b.Fatalf("prune removed %d/%d roots; %d results remain", report.RemovedPersistedRootCount, before, len(f.cache.resultsByID))
				}
				f.close(b)
			}
		})
	}
}
