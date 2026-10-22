package dagql

import (
	"context"
	"fmt"
	"testing"

	"github.com/dagger/dagger/dagql/call"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
)

func TestImportedClassMembership(t *testing.T) {
	c := &Cache{}
	c.initEgraphLocked()
	// Leave one dead class so compaction has to renumber the live classes.
	c.ensureEqClassForDigestLocked(t.Context(), "dead")
	left := c.ensureEqClassForDigestLocked(t.Context(), "left")
	right := c.ensureEqClassForDigestLocked(t.Context(), "right")
	a := &sharedResult{id: 1, imported: true}
	b := &sharedResult{id: 2}
	c.putResultLocked(a)
	c.putResultLocked(b)
	c.addResultOutputEqClassLocked(a.id, left)
	c.addResultOutputEqClassLocked(a.id, left)
	c.addResultOutputEqClassLocked(a.id, right)
	c.addResultOutputEqClassLocked(b.id, right)
	require.Equal(t, map[eqClassID]int{left: 1, right: 1}, c.outputEqClassImported)

	root, _ := c.mergeEqClassesNoRepairLocked(left, right)
	require.Equal(t, map[eqClassID]int{root: 1}, c.outputEqClassImported, "overlapping membership is counted once")
	c.setResultImportedLocked(b, true)
	c.setResultImportedLocked(b, true)
	require.Equal(t, 2, c.outputEqClassImported[root])
	c.setResultImportedLocked(a, false)
	require.Equal(t, 1, c.outputEqClassImported[root])
	c.compactEqClassesLocked(true)
	for class := range c.outputEqClassRootsLocked(b.id) {
		root = class
	}
	require.Equal(t, map[eqClassID]int{root: 1}, c.outputEqClassImported)
	c.removeResultOutputEqClassesLocked(b.id)
	require.Empty(t, c.outputEqClassImported)

	c.setResultImportedLocked(a, true)
	c.removeResultOutputEqClassesLocked(a.id)
	c.deleteResultLocked(a)
	c.deleteResultLocked(b)
	c.maybeResetEgraphLocked()
	require.Nil(t, c.outputEqClassImported)
}

// Distinct calls returning equivalent values grow one output class. Sharing
// is enabled, but these locally computed values have no imported receiver.
func BenchmarkPublishNativeEquivalentResults(b *testing.B) {
	for _, count := range []int{128, 512, 2048, 8192} {
		b.Run(fmt.Sprint(count), func(b *testing.B) {
			b.ReportAllocs()
			for range b.N {
				b.StopTimer()
				c, ctx := newCacheDerivedIndexFixtureCache(b, "native-equivalents", "")
				require.NoError(b, c.EnableSnapshotSharing())
				b.StartTimer()
				for i := range count {
					request := cacheTestIntCall(fmt.Sprintf("native-%d", i))
					response := cacheTestIntCall(request.Field, call.ExtraDigest{
						Label: call.ExtraDigestLabelContent, Digest: digest.FromString("same-value"),
					})
					_, err := c.GetOrInitCall(ctx, "native-equivalents", noopTypeResolver{}, &CallRequest{
						ResultCall: request,
					}, func(context.Context) (AnyResult, error) {
						return cacheTestIntResult(response, 1), nil
					})
					require.NoError(b, err)
				}
				b.StopTimer()
				largest := 0
				for _, members := range c.outputEqClassResults {
					if len(members) > largest {
						largest = len(members)
					}
				}
				require.Equal(b, count, largest)
				require.NoError(b, c.CloseDiscardingPersistence())
				b.StartTimer()
			}
		})
	}
}
