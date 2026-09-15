package dagql

import (
	"cmp"
	"context"
	"errors"
	"fmt"
	"net/url"
	"slices"

	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/opencontainers/go-digest"
)

// PersistedContentRefLink names a content root owned directly by a result.
// It is a storage relationship, not a child result or an egraph equivalence.
// Each role has one root; the content store owns its transitive GC links.
type PersistedContentRefLink struct {
	Digest digest.Digest
	Role   string
}

type PersistedContentRefLinkProvider interface {
	PersistedContentRefLinks() []PersistedContentRefLink
}

// ContentOperationLeasePolicy lets types with both snapshot-backed and
// content-backed values keep ordinary lazy operations on the existing lease
// path. Content providers default to requiring a content operation lease:
// their roots may only become known after the lazy callback has run.
type ContentOperationLeasePolicy interface {
	NeedsContentOperationLease() bool
}

func needsContentOperationLease(self Typed) bool {
	if policy, ok := self.(ContentOperationLeasePolicy); ok {
		return policy.NeedsContentOperationLease()
	}
	_, ok := self.(PersistedContentRefLinkProvider)
	return ok
}

func contentOwnerLinksFromTyped(self Typed) []PersistedContentRefLink {
	if provider, ok := self.(PersistedContentRefLinkProvider); ok {
		return slices.Clone(provider.PersistedContentRefLinks())
	}
	return nil
}

func desiredContentLinksForResult(res *sharedResult) []PersistedContentRefLink {
	state := res.loadPayloadState()
	if state.hasValue && state.self != nil {
		return contentOwnerLinksFromTyped(state.self)
	}
	return state.contentOwnerLinks
}

func normalizeContentLinks(links []PersistedContentRefLink) ([]PersistedContentRefLink, error) {
	links = slices.Clone(links)
	slices.SortFunc(links, func(a, b PersistedContentRefLink) int {
		return cmp.Compare(a.Role, b.Role)
	})
	for i, link := range links {
		if link.Role == "" {
			return nil, errors.New("content owner link has an empty role")
		}
		if err := link.Digest.Validate(); err != nil {
			return nil, fmt.Errorf("content owner role %q: %w", link.Role, err)
		}
		if i > 0 && links[i-1].Role == link.Role && links[i-1].Digest != link.Digest {
			return nil, fmt.Errorf("conflicting content roots for role %q", link.Role)
		}
	}
	return slices.Compact(links), nil
}

func resultContentLeaseID(resultID sharedResultID, link PersistedContentRefLink) string {
	// Snapshot roles occupy exactly one escaped path component after the ID.
	// A separate content component prevents collisions; including the digest
	// lets a replacement attach the new root before dropping the old one.
	return fmt.Sprintf("dagql/result/%d/content/%s/%s", resultID, url.PathEscape(link.Role), link.Digest)
}

func (c *Cache) resultOwnerLeaseCleanup(res *sharedResult) OnReleaseFunc {
	return joinOnRelease(c.resultSnapshotLeaseCleanup(res), func(ctx context.Context) error {
		if res.id == 0 {
			return nil
		}
		res.contentOwnerMu.Lock()
		defer res.contentOwnerMu.Unlock()
		var rerr error
		if c.snapshotManager != nil {
			for _, link := range res.loadPayloadState().contentOwnerLinks {
				rerr = errors.Join(rerr, c.snapshotManager.RemoveLease(ctx, resultContentLeaseID(res.id, link)))
			}
		}
		return errors.Join(rerr, releaseContentHandoffs(ctx, res))
	})
}

func (c *Cache) syncResultOwnerLeases(ctx context.Context, res *sharedResult) error {
	if err := c.syncResultSnapshotLeases(ctx, res); err != nil {
		return err
	}
	return c.syncResultContentLeases(ctx, res)
}

func (c *Cache) syncResultContentLeases(ctx context.Context, res *sharedResult) error {
	if res == nil || res.id == 0 {
		return nil
	}
	desired, err := normalizeContentLinks(desiredContentLinksForResult(res))
	if err != nil {
		return err
	}
	old := res.loadPayloadState().contentOwnerLinks
	if len(desired) == 0 && len(old) == 0 {
		if _, ok := res.loadPayloadState().self.(PersistedContentRefLinkProvider); !ok {
			return nil
		}
		res.contentOwnerMu.Lock()
		defer res.contentOwnerMu.Unlock()
		return releaseContentHandoffs(context.WithoutCancel(ctx), res)
	}
	res.contentOwnerMu.Lock()
	defer res.contentOwnerMu.Unlock()
	desired, err = normalizeContentLinks(desiredContentLinksForResult(res))
	if err != nil {
		return err
	}
	old = res.loadPayloadState().contentOwnerLinks
	manager, ok := c.snapshotManager.(bkcache.ContentManager)
	if !ok {
		return errors.New("cache storage does not support content-root ownership")
	}
	c.setContentOwnerDirty(res, true)
	// Keep every attempted lease in cleanup state, even if attachment fails
	// partway through. Retry and result release can both safely remove it.
	attached := slices.Clone(old)
	for _, link := range desired {
		if !slices.Contains(attached, link) {
			attached = append(attached, link)
			c.storeContentOwnerLinks(res, attached)
		}
		// Also ensure previously attempted links: an earlier attach and its
		// cleanup may both have failed. The manager operation is idempotent.
		if err := manager.AttachContentLease(ctx, resultContentLeaseID(res.id, link), link.Digest); err != nil {
			// The manager rolls back newly introduced ownership. Do not remove
			// an existing valid lease on a transient failure to inspect it.
			return err
		}
	}
	for _, link := range old {
		if !slices.Contains(desired, link) {
			if err := c.snapshotManager.RemoveLease(ctx, resultContentLeaseID(res.id, link)); err != nil {
				return err
			}
		}
	}
	c.storeContentOwnerLinks(res, desired)
	c.setContentOwnerDirty(res, false)
	return releaseContentHandoffs(context.WithoutCancel(ctx), res)
}

// A consumed CAS-producing lazy callback cannot be replayed after a handoff
// failure. Its temporary lease therefore follows the result lifecycle instead
// of an operation timeout. Orphaned leases share the result-owner prefix and
// are removed by the existing startup reconciliation.
func (c *Cache) withResultOperationLease(ctx context.Context, res *sharedResult) (context.Context, func(context.Context) error, error) {
	ctx = withoutOperationLease(ctx)
	if !needsContentOperationLease(res.loadPayloadState().self) {
		return withOperationLease(ctx)
	}
	manager, ok := c.snapshotManager.(bkcache.ContentManager)
	if !ok {
		return nil, nil, errors.New("cache storage does not support content-root ownership")
	}
	return manager.WithContentOperationLease(ctx, fmt.Sprintf("dagql/result/%d/content-operation/", res.id))
}

// Caller holds contentOwnerMu. Keep unsuccessful releases available for retry.
func releaseContentHandoffs(ctx context.Context, res *sharedResult) error {
	var rerr error
	var pending []OnReleaseFunc
	for _, release := range res.contentHandoffReleases {
		if err := release(ctx); err != nil {
			rerr = errors.Join(rerr, err)
			pending = append(pending, release)
		}
	}
	res.contentHandoffReleases = pending
	return rerr
}

func (c *Cache) setContentOwnerDirty(res *sharedResult, dirty bool) {
	c.egraphMu.Lock()
	defer c.egraphMu.Unlock()
	res.payloadMu.Lock()
	res.contentOwnerDirty = dirty
	res.payloadMu.Unlock()
}

func (c *Cache) storeContentOwnerLinks(res *sharedResult, links []PersistedContentRefLink) {
	c.egraphMu.Lock()
	defer c.egraphMu.Unlock()
	res.payloadMu.Lock()
	if slices.Equal(res.contentOwnerLinks, links) {
		res.payloadMu.Unlock()
		return
	}
	res.contentOwnerLinks = slices.Clone(links)
	res.payloadMu.Unlock()
	// Expanded physical identities are derived at usage/prune time, not in
	// the publication hot path. Invalidate them whenever ownership changes.
	res.contentUsageIdentities = nil
	for identity := range res.cacheUsageSizeByIdentity {
		if isContentUsageIdentity(identity) {
			delete(res.cacheUsageSizeByIdentity, identity)
			delete(res.cacheUsageRecordTypeByID, identity)
		}
	}
}
