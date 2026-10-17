package dagql

import (
	"fmt"
	"runtime"
	"testing"
	"time"

	"github.com/dagger/dagger/dagql/call"
	"github.com/opencontainers/go-digest"
)

// This synthetic index fixture isolates compaction. Construction is outside
// the timer; ordinary GC remains enabled. Complete-command timing is separate.
func BenchmarkCompactionOwnership(b *testing.B) {
	for _, shape := range []struct {
		name       string
		live, dead int
	}{
		{"small", 1000, 1000},
		{"large", 200000, 40000},
		{"sparse", 2000, 1000000},
	} {
		b.Run(shape.name, func(b *testing.B) {
			b.ReportAllocs()
			var hold time.Duration
			for range b.N {
				b.StopTimer()
				c := &Cache{}
				c.initEgraphLocked()
				c.egraphParents = make([]eqClassID, shape.live+shape.dead+1)
				c.egraphRanks = make([]uint8, len(c.egraphParents))
				for i := 1; i < len(c.egraphParents); i++ {
					c.egraphParents[i] = eqClassID(i)
				}
				for i := range shape.live {
					id := eqClassID(shape.dead + i + 1)
					text := fmt.Sprintf("compaction-class-%d", i)
					c.eqClassToDigests[id] = map[string]struct{}{text: {}, text + "-alias": {}}
					c.egraphDigestToClass[text] = id
					c.egraphDigestToClass[text+"-alias"] = id
					if i%8 == 0 {
						c.eqClassExtraDigests[id] = map[call.ExtraDigest]struct{}{{Label: "content", Digest: digest.FromString(text)}: {}}
					}
					for j := range 2 {
						termID := egraphTermID(2*i + j + 1)
						inputs := []eqClassID{eqClassID(shape.dead + (i+shape.live-1)%shape.live + 1), id}
						c.egraphTerms[termID] = newEgraphTerm(termID, digest.FromString(fmt.Sprintf("operation-%d-%d", i, j)), inputs, id)
					}
				}
				b.StartTimer()
				c.egraphMu.Lock()
				started := time.Now()
				changed, oldSlots, newSlots := c.compactEqClassesLocked(true)
				c.egraphMu.Unlock()
				hold += time.Since(started)
				b.StopTimer()
				if !changed || oldSlots != shape.live+shape.dead || newSlots != shape.live || len(c.egraphTerms) != 2*shape.live || len(c.egraphDigestToClass) != 2*shape.live {
					b.Fatalf("unexpected compacted population: changed=%v, slots=%d→%d, terms=%d, digests=%d", changed, oldSlots, newSlots, len(c.egraphTerms), len(c.egraphDigestToClass))
				}
				for _, term := range c.egraphTerms {
					if len(term.inputEqIDs) != 2 || term.termDigest != calcEgraphTermDigest(term.selfDigest, term.inputEqIDs) || term.outputEqID == 0 || int(term.outputEqID) > shape.live {
						b.Fatal("compaction changed the term structure")
					}
				}
				runtime.KeepAlive(c)
			}
			b.ReportMetric(float64(hold.Nanoseconds())/float64(b.N), "write-lock-hold-ns")
		})
	}
}
