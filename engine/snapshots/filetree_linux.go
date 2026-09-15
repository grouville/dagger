//go:build linux

package snapshots

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"

	"github.com/containerd/containerd/v2/core/leases"
	ctdsnapshots "github.com/containerd/containerd/v2/core/snapshots"
	"github.com/containerd/errdefs"
	"github.com/dagger/dagger/engine/filetree"
	"github.com/dagger/dagger/engine/wcprof"
)

// FileTreeManager derives disposable filesystem views from result-owned CAS
// roots. The caller retains the operation lease until the result owns its root
// and any materialized snapshot. It must not use a flat snapshot-owner lease.
type FileTreeManager interface {
	FileTreeIngest(context.Context) (*filetree.Ingest, error)
	FileTreeRoot(context.Context, string) (filetree.Object, error)
	MaterializeFileTree(context.Context, filetree.Object, string, ...RefOption) (ImmutableRef, error)
}

var _ FileTreeManager = (*snapshotManager)(nil)

const fileTreeRootKey = "filetree.root.v1"
const fileTreeRootIndex = "filetree.root.v1:"
const fileTreeRootLabel = "dagger.io/filetree.root.v1"
const fileTreeSourceIndex = "filetree.source:"

type fileTreeSourceKey string

// WithFileTreeSourceKey supplies only a locality hint for a derived view. It
// creates neither ownership nor content equivalence. GC may remove all matches.
func WithFileTreeSourceKey(key string) RefOption { return fileTreeSourceKey(key) }

func (cm *snapshotManager) FileTreeIngest(ctx context.Context) (*filetree.Ingest, error) {
	if cm.ContentStore == nil || cm.LeaseManager == nil {
		return nil, errors.New("filetree requires a content store and lease manager")
	}
	ctx, err := EnsureLease(ctx)
	if err != nil {
		return nil, err
	}
	return filetree.NewStore(cm.ContentStore).Ingest(ctx, cm.LeaseManager)
}

// FileTreeRoot resolves an optional derived-view hint and retains its complete
// content tree in the caller's operation lease. The view itself is not retained:
// callers publish the returned root, never rely on the view remaining available.
// A legacy view without a root label is a miss, just like a collected view/root.
func (cm *snapshotManager) FileTreeRoot(ctx context.Context, snapshotID string) (filetree.Object, error) {
	info, err := cm.Snapshotter.Stat(ctx, snapshotID)
	if err != nil {
		return filetree.Object{}, err
	}
	payload := info.Labels[fileTreeRootLabel]
	if payload == "" {
		return filetree.Object{}, fmt.Errorf("snapshot %s has no filetree root: %w", snapshotID, errNotFound)
	}
	var root filetree.Object
	if err := json.Unmarshal([]byte(payload), &root); err != nil {
		return filetree.Object{}, fmt.Errorf("decode filetree root: %w", err)
	}
	in, err := cm.FileTreeIngest(ctx)
	if err != nil {
		return filetree.Object{}, err
	}
	if err := in.Retain(root); err != nil {
		return filetree.Object{}, err
	}
	// A surviving snapshot is not evidence that all CAS objects still exist.
	// Check the canonical tree/GC links and leaf availability before choosing
	// this root instead of re-ingesting the current, conflict-held mirror.
	if _, err := filetree.NewView(ctx, filetree.NewStore(cm.ContentStore), root); err != nil {
		return filetree.Object{}, err
	}
	if _, err := cm.ContentUsage(ctx, root.Digest); err != nil {
		return filetree.Object{}, err
	}
	return root, nil
}

// MaterializeFileTree reconstructs root, optionally reusing a previous immutable
// view. The previous snapshot ID is only a hint: missing snapshots, absent root
// metadata, and collected previous manifests fall back to full reconstruction.
// Current root errors never fall back to a stale filesystem view.
func (cm *snapshotManager) MaterializeFileTree(ctx context.Context, root filetree.Object, previousSnapshotID string, opts ...RefOption) (_ ImmutableRef, rerr error) {
	var sourceKey string
	for _, opt := range opts {
		if key, ok := opt.(fileTreeSourceKey); ok {
			sourceKey = string(key)
		}
	}
	ctx, err := EnsureLease(ctx)
	if err != nil {
		return nil, err
	}
	in, err := cm.FileTreeIngest(ctx)
	if err != nil {
		return nil, err
	}
	if err := in.Retain(root); err != nil {
		return nil, err
	}
	store := filetree.NewStore(cm.ContentStore)
	indexCtx, indexOp := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filetree.view.index", wcprof.OpOpts{})
	after, err := filetree.NewView(indexCtx, store, root)
	indexOp.EndErr(err)
	if err != nil {
		return nil, err
	}

	// Serialize identical reconstructions using the manager's existing keyed
	// materialization lock. The index is snapshot metadata, not extra ownership.
	key := fileTreeRootIndex + root.Digest.String()
	cm.importLayerLocker.Lock(key)
	defer cm.importLayerLocker.Unlock(key)
	matches, err := cm.Search(ctx, key, false)
	if err != nil {
		return nil, err
	}
	for _, md := range matches {
		ref, err := cm.retainFileTreeSnapshot(ctx, md.SnapshotID(), opts...)
		if err == nil {
			return ref, nil
		}
		if !IsNotFound(err) {
			return nil, err
		}
	}
	if previousSnapshotID == "" && sourceKey != "" {
		matches, err := cm.Search(ctx, fileTreeSourceIndex+sourceKey, false)
		if err != nil {
			return nil, err
		}
		slices.SortFunc(matches, func(a, b RefMetadata) int { return b.GetCreatedAt().Compare(a.GetCreatedAt()) })
		if len(matches) > 0 {
			previousSnapshotID = matches[0].SnapshotID()
		}
	}

	var parent ImmutableRef
	var before *filetree.View
	// Delta application assumes preparing a child preserves the parent's
	// metadata. The native snapshotter copies directories before their children,
	// changing directory mtimes (and tolerates xattr-copy failures). Reconstruct
	// there instead; only enable parent reuse on the verified CoW backend.
	if previousSnapshotID != "" && cm.Snapshotter.Name() == "overlayfs" {
		parent, err = cm.retainFileTreeSnapshot(ctx, previousSnapshotID)
		if err != nil && !IsNotFound(err) {
			return nil, err
		}
		if parent != nil {
			defer func() { rerr = errors.Join(rerr, parent.Release(context.WithoutCancel(ctx))) }()
			info, err := cm.Snapshotter.Stat(ctx, parent.SnapshotID())
			if err != nil {
				return nil, err
			}
			previous := info.Labels[fileTreeRootLabel]
			if previous != "" {
				var obj filetree.Object
				if err := json.Unmarshal([]byte(previous), &obj); err != nil {
					return nil, fmt.Errorf("decode previous filetree root: %w", err)
				}
				if err := in.Retain(obj); err == nil {
					indexCtx, indexOp := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filetree.view.parentIndex", wcprof.OpOpts{})
					before, err = filetree.NewView(indexCtx, store, obj)
					indexOp.EndErr(err)
					if err != nil && !errdefs.IsNotFound(err) {
						return nil, err
					}
				} else if !errdefs.IsNotFound(err) {
					return nil, err
				}
			}
		}
	}
	base := parent
	if before == nil {
		base = nil
	}
	mut, err := cm.New(ctx, base, opts...)
	if err != nil {
		return nil, err
	}
	defer func() {
		if mut != nil {
			rerr = errors.Join(rerr, mut.Release(context.WithoutCancel(ctx)))
		}
	}()
	mountable, err := mut.Mount(ctx, false)
	if err != nil {
		return nil, err
	}
	mounter := LocalMounter(mountable)
	defer func() {
		if mounter != nil {
			rerr = errors.Join(rerr, mounter.Unmount())
		}
	}()
	destination, err := mounter.Mount()
	if err != nil {
		return nil, err
	}
	applyCtx, applyOp := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filetree.view.apply", wcprof.OpOpts{})
	err = filetree.Materialize(applyCtx, destination, before, after)
	applyOp.EndErr(err)
	if err != nil {
		return nil, err
	}
	if err := mounter.Unmount(); err != nil {
		return nil, err
	}
	mounter = nil
	commitCtx, commitOp := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filetree.view.commit", wcprof.OpOpts{})
	ref, err := mut.Commit(commitCtx)
	commitOp.EndErr(err)
	if err != nil {
		return nil, err
	}
	mut = nil
	defer func() {
		if rerr != nil {
			rerr = errors.Join(rerr, ref.Release(context.WithoutCancel(ctx)))
		}
	}()
	payload, err := json.Marshal(root)
	if err != nil {
		return nil, err
	}
	if err := ref.(*immutableRef).SetString(fileTreeRootKey, string(payload), key); err != nil {
		return nil, err
	}
	if sourceKey != "" {
		if err := ref.(*immutableRef).SetString("filetree.source", sourceKey, fileTreeSourceIndex+sourceKey); err != nil {
			return nil, err
		}
	}
	// The snapshot hint survives a manager restart. This label describes the
	// derived view; it is deliberately not a content GC edge or root ownership.
	if _, err := cm.Snapshotter.Update(ctx, ctdsnapshots.Info{
		Name: ref.SnapshotID(), Labels: map[string]string{fileTreeRootLabel: string(payload)},
	}, "labels."+fileTreeRootLabel); err != nil {
		return nil, err
	}
	return ref, nil
}

func (cm *snapshotManager) retainFileTreeSnapshot(ctx context.Context, id string, opts ...RefOption) (ImmutableRef, error) {
	leaseID, ok := leases.FromContext(ctx)
	if !ok || leaseID == "" {
		return nil, errors.New("filetree snapshot reuse requires an operation lease")
	}
	// In-memory references are not GC ownership. Pin before lookup to close the
	// gap between the previous result disappearing and the next result attaching.
	if err := cm.LeaseManager.AddResource(ctx, leases.Lease{ID: leaseID}, leases.Resource{
		Type: "snapshots/" + cm.Snapshotter.Name(), ID: id,
	}); err != nil {
		if errdefs.IsNotFound(err) {
			return nil, fmt.Errorf("filetree snapshot %s: %w", id, errNotFound)
		}
		return nil, err
	}
	return cm.GetBySnapshotID(ctx, id, opts...)
}
