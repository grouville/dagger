package dagql

import (
	"fmt"
	"testing"

	"github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
)

func TestCompactEqClassesKeepsSparseReferences(t *testing.T) {
	c := &Cache{}
	c.initEgraphLocked()
	ids := make([]eqClassID, 4099)
	for i := 1; i < len(ids); i++ {
		ids[i] = c.ensureEqClassForDigestLocked(t.Context(), fmt.Sprintf("mapping-%d", i))
	}
	live := []int{1, 31, 32, 63, 64, 65, 127, 128, 129, 255, 256, 257, 1023, 1024, 1025, 4095, 4096}
	for i, index := range live {
		id := egraphTermID(i + 1)
		inputs := []eqClassID{ids[live[(i+1)%len(live)]], ids[index]}
		c.egraphTerms[id] = newEgraphTerm(id, digest.FromString(fmt.Sprint(i)), inputs, ids[index])
	}
	// These classes are live solely through a result, without any term edge.
	c.resultOutputEqClasses[1000] = map[eqClassID]struct{}{ids[66]: {}, ids[2048]: {}}
	before := testEqClassContentsLocked(c)
	changed, oldSlots, newSlots := c.compactEqClassesLocked(true)
	assert.Assert(t, changed)
	assert.Equal(t, oldSlots, len(ids)-1)
	assert.Equal(t, newSlots, len(live)+2)
	assert.DeepEqual(t, before, testEqClassContentsLocked(c))
}
