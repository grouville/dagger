package dagql

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"testing"

	"github.com/opencontainers/go-digest"
	"gotest.tools/v3/assert"
)

func TestCompactionPreservesSnapshotsAcrossLaterMerges(t *testing.T) {
	baseCtx := t.Context()
	c, err := NewCache(baseCtx, "", nil, nil)
	assert.NilError(t, err)
	t.Cleanup(func() { assert.NilError(t, c.CloseDiscardingPersistence()) })
	ctxA := cacheTestSessionContext(baseCtx, "compaction-owner-a")
	ctxB := cacheTestSessionContext(baseCtx, "compaction-owner-b")
	a := cacheTestPublishContentResult(t, c, ctxA, "compaction-owner-a", 7, digest.FromString("compaction-owner-a"))
	b := cacheTestPublishContentResult(t, c, ctxB, "compaction-owner-b", 7, digest.FromString("compaction-owner-b"))
	parentCall, err := a.ResultCall()
	assert.NilError(t, err)
	childCall := cacheTestIntCall("compaction-owner-child")
	childCall.Receiver = &ResultCallRef{Call: parentCall}
	child, err := c.GetOrInitCall(ctxA, "compaction-owner-a", noopTypeResolver{}, &CallRequest{ResultCall: childCall}, ValueFunc(cacheTestIntResult(childCall, 3)))
	assert.NilError(t, err)
	for _, result := range []AnyResult{a, b, child} {
		assert.NilError(t, c.MakeResultUnpruneable(baseCtx, result))
	}
	snapshot, err := c.snapshotPersistState(baseCtx)
	assert.NilError(t, err)
	terms := slices.Clone(snapshot.terms)
	inputs := slices.Clone(snapshot.termInputs)
	digests := slices.Clone(snapshot.eqClassDigests)
	assert.Assert(t, len(inputs) > 0)
	assert.Assert(t, len(digests) > 0)

	compact := func(round int) {
		c.egraphMu.Lock()
		for i := range 16 {
			c.ensureEqClassForDigestLocked(baseCtx, fmt.Sprintf("compaction-unused-%d-%d", round, i))
		}
		changed, oldSlots, newSlots := c.compactEqClassesLocked(true)
		indexErr := cacheDerivedIndexesErrorLocked(c)
		c.egraphMu.Unlock()
		assert.Assert(t, changed)
		assert.Assert(t, oldSlots > newSlots)
		assert.NilError(t, indexErr)
	}
	compact(0)
	c.egraphMu.Lock()
	var rootA, rootB eqClassID
	for rootA = range c.outputEqClassesForResultLocked(a.cacheSharedResult().id) {
	}
	for rootB = range c.outputEqClassesForResultLocked(b.cacheSharedResult().id) {
	}
	distinct := rootA != rootB
	c.mergeEqClassesLocked(baseCtx, rootA, rootB)
	indexErr := cacheDerivedIndexesErrorLocked(c)
	c.egraphMu.Unlock()
	assert.Assert(t, distinct)
	assert.NilError(t, indexErr)
	compact(1)

	// Saved rows must remain independent of later remapping and term repair.
	assert.DeepEqual(t, snapshot.terms, terms)
	assert.DeepEqual(t, snapshot.termInputs, inputs)
	assert.DeepEqual(t, snapshot.eqClassDigests, digests)
	hit, err := c.GetOrInitCall(ctxA, "compaction-owner-a", noopTypeResolver{}, &CallRequest{ResultCall: childCall}, func(context.Context) (AnyResult, error) {
		return nil, errors.New("the child should remain cached after compaction and merging")
	})
	assert.NilError(t, err)
	assert.Assert(t, hit.HitCache())
	assert.Equal(t, hit.cacheSharedResult().id, child.cacheSharedResult().id)
	assert.NilError(t, c.ReleaseSession(ctxA, "compaction-owner-a"))
	assert.NilError(t, c.ReleaseSession(ctxB, "compaction-owner-b"))
}
