package dagql

import (
	"iter"
	"maps"

	set "github.com/hashicorp/go-set/v3"
)

// resultDigestPosting combines a digest's runtime postings with a snapshot of
// its output class at import. All digests of that class share the snapshot;
// copying its results once per digest would take quadratic space.
//
// Runtime insertions stay local to the digest. Removal is only used when a
// result is collected globally, so it also removes the result from the shared
// snapshot. All access is protected by Cache.egraphMu.
type resultDigestPosting struct {
	exact    *set.TreeSet[sharedResultID]
	imported map[sharedResultID]struct{}
}

func (p *resultDigestPosting) Contains(id sharedResultID) bool {
	_, ok := p.imported[id]
	return ok || p.exact != nil && p.exact.Contains(id)
}

func (p *resultDigestPosting) Insert(id sharedResultID) bool {
	if p.Contains(id) {
		return false
	}
	if p.exact == nil {
		p.exact = newSharedResultIDSet()
	}
	return p.exact.Insert(id)
}

func (p *resultDigestPosting) Remove(id sharedResultID) {
	delete(p.imported, id)
	if p.exact != nil {
		p.exact.Remove(id)
	}
}

func (p *resultDigestPosting) Size() int {
	n := len(p.imported)
	if p.exact != nil {
		n += p.exact.Size()
	}
	return n
}

func (p *resultDigestPosting) Empty() bool {
	return p.Size() == 0
}

// Items yields each result once. Callers sort candidates in their own set;
// iteration order within an individual posting has no meaning.
func (p *resultDigestPosting) Items() iter.Seq[sharedResultID] {
	return func(yield func(sharedResultID) bool) {
		for id := range p.imported {
			if !yield(id) {
				return
			}
		}
		if p.exact != nil {
			for id := range p.exact.Items() {
				if !yield(id) {
					return
				}
			}
		}
	}
}

// restoreDigestPostingsLocked requires egraphMu. Capture membership at import:
// later unions must not silently broaden the postings of an existing digest.
func (c *Cache) restoreDigestPostingsLocked() {
	for outputEqID, resultIDs := range c.outputEqClassResults {
		imported := maps.Clone(resultIDs)
		for resultID := range imported {
			c.markResultBroadlyIndexedLocked(resultID)
		}
		for dig := range c.eqClassToDigests[outputEqID] {
			c.egraphResultsByDigest[dig] = &resultDigestPosting{imported: imported}
		}
	}
}
