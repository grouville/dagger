package snapshots

import (
	"cmp"
	"context"
	"errors"
	"fmt"
	"slices"
	"strconv"
	"strings"
	"time"

	"github.com/containerd/containerd/v2/core/leases"
	cerrdefs "github.com/containerd/errdefs"
	"github.com/opencontainers/go-digest"
)

// ContentManager is an optional capability for result-owned content graphs,
// independent of snapshot ownership. RemoveLease releases either kind of owner.
type ContentManager interface {
	WithContentOperationLease(context.Context, string) (context.Context, func(context.Context) error, error)
	AttachContentLease(context.Context, string, digest.Digest) error
	ContentUsage(context.Context, digest.Digest) ([]ContentUsage, error)
}

type ContentUsage struct {
	Digest digest.Digest
	Size   int64
}

var _ ContentManager = (*snapshotManager)(nil)

// WithContentOperationLease lazily creates non-expiring ownership for a content
// operation whose handoff may need retrying after its callback has completed.
// The caller must use a result-scoped prefix recognized by stale-owner cleanup,
// retain the release callback until handoff or abandonment, and supply a context
// with any outer operation lease cleared. Like WithLazyLease, an existing lease
// or lazy scope is borrowed unchanged and its release callback is a no-op.
func (cm *snapshotManager) WithContentOperationLease(ctx context.Context, leasePrefix string) (context.Context, func(context.Context) error, error) {
	if leasePrefix == "" {
		return ctx, nil, errors.New("content operation lease: empty prefix")
	}
	return WithLazyLease(ctx, cm.LeaseManager, func(l *leases.Lease) error {
		// NewLease applies these options after choosing a random ID and setting
		// its normal operation timeout. Result ownership replaces that timeout.
		l.ID = leasePrefix + l.ID
		delete(l.Labels, "containerd.io/gc.expire")
		return nil
	})
}

// AttachContentLease owns one content root and its outgoing GC references. The
// caller uses a distinct lease ID per result/role/digest and retains its operation
// lease until attachment succeeds. This permits new-before-old replacement.
// Existing snapshot owner leases remain flat and must not be reused here.
func (cm *snapshotManager) AttachContentLease(ctx context.Context, leaseID string, root digest.Digest) (rerr error) {
	if leaseID == "" {
		return errors.New("attach content lease: empty lease ID")
	}
	if err := root.Validate(); err != nil {
		return fmt.Errorf("attach content lease: invalid root digest: %w", err)
	}
	if err := context.Cause(ctx); err != nil {
		return err
	}
	cm.ownerLeaseLocker.Lock(leaseID)
	defer cm.ownerLeaseLocker.Unlock(leaseID)

	lease, err := cm.LeaseManager.Create(ctx, leases.WithID(leaseID))
	created := err == nil
	if err != nil && !cerrdefs.IsAlreadyExists(err) {
		return fmt.Errorf("create content owner lease: %w", err)
	}
	resource := leases.Resource{Type: "content", ID: root.String()}
	var added bool
	defer func() {
		if rerr == nil || (!created && !added) {
			return
		}
		cleanupCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
		defer cancel()
		var err error
		if created {
			err = cm.LeaseManager.Delete(cleanupCtx, leases.Lease{ID: leaseID})
		} else {
			// Preserve an existing lease and any pre-existing ownership.
			err = cm.LeaseManager.DeleteResource(cleanupCtx, lease, resource)
		}
		if err != nil && !cerrdefs.IsNotFound(err) {
			rerr = errors.Join(rerr, fmt.Errorf("clean up failed content attachment: %w", err))
		}
	}()

	var alreadyOwned bool
	if !created {
		matches, err := cm.LeaseManager.List(ctx, "id=="+strconv.Quote(leaseID))
		if err != nil {
			return fmt.Errorf("inspect content owner lease: %w", err)
		}
		if len(matches) != 1 || matches[0].ID != leaseID {
			return fmt.Errorf("content owner lease %q: %w", leaseID, cerrdefs.ErrNotFound)
		}
		lease = matches[0]
		if _, flat := lease.Labels["containerd.io/gc.flat"]; flat {
			return errors.New("content owner lease must not be flat")
		}
		if _, expiring := lease.Labels["containerd.io/gc.expire"]; expiring {
			return errors.New("content owner lease must not expire independently of its result")
		}
		resources, err := cm.LeaseManager.ListResources(ctx, lease)
		if err != nil {
			return fmt.Errorf("inspect content owner resources: %w", err)
		}
		for _, existing := range resources {
			if existing != resource {
				return fmt.Errorf("content owner lease %q already owns a different resource", leaseID)
			}
			alreadyOwned = true
		}
	}
	if !alreadyOwned {
		if err := cm.LeaseManager.AddResource(ctx, lease, resource); err != nil {
			return fmt.Errorf("attach content root %s: %w", root, err)
		}
		added = true
	}
	// Pin before checking availability, avoiding an unowned lookup/publication gap.
	if _, err := cm.ContentStore.Info(ctx, root); err != nil {
		return fmt.Errorf("inspect content root %s: %w", root, err)
	}
	return nil
}

// ContentUsage reports each physical blob once, not a summed size per root.
// The caller retains the root for this walk; this method does not create leases.
// It follows the same exact, '.'- and '/'-suffixed content labels as containerd.
func (cm *snapshotManager) ContentUsage(ctx context.Context, root digest.Digest) ([]ContentUsage, error) {
	if err := root.Validate(); err != nil {
		return nil, fmt.Errorf("content usage: invalid root digest: %w", err)
	}
	const contentRefLabel = "containerd.io/gc.ref.content"
	seen := map[digest.Digest]struct{}{root: {}}
	pending := []digest.Digest{root}
	var usage []ContentUsage
	for len(pending) > 0 {
		if err := context.Cause(ctx); err != nil {
			return nil, err
		}
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		info, err := cm.ContentStore.Info(ctx, current)
		if err != nil {
			return nil, fmt.Errorf("inspect content usage %s: %w", current, err)
		}
		if info.Size < 0 {
			return nil, fmt.Errorf("negative content size for %s", current)
		}
		usage = append(usage, ContentUsage{Digest: current, Size: info.Size})
		for key, value := range info.Labels {
			if err := context.Cause(ctx); err != nil {
				return nil, err
			}
			if key != contentRefLabel && !strings.HasPrefix(key, contentRefLabel+".") && !strings.HasPrefix(key, contentRefLabel+"/") {
				continue
			}
			child := digest.Digest(value)
			if err := child.Validate(); err != nil {
				return nil, fmt.Errorf("content %s label %q: invalid child digest: %w", current, key, err)
			}
			if _, exists := seen[child]; !exists {
				seen[child] = struct{}{}
				pending = append(pending, child)
			}
		}
	}
	slices.SortFunc(usage, func(a, b ContentUsage) int { return cmp.Compare(a.Digest, b.Digest) })
	return usage, nil
}
