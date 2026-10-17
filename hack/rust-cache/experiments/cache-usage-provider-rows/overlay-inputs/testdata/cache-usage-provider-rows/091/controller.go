package server

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/pkg/namespaces"
	cerrdefs "github.com/containerd/errdefs"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/wcprof"
)

// Diagnostic only. All mutation is limited to collector mode or a new scratch
// snapshot; no prune policy or existing cache root is removed by this endpoint.
func (srv *Server) SnapshotCollectionDiagnostic(ctx context.Context, action string, deferred, drain bool, files int, snapshotID string) (_ map[string]any, rerr error) {
	if action == "status" {
		status := srv.snapshotGarbage.diagnosticState()
		status["metadata_estimate"] = srv.engineCache.MetadataEstimate()
		status["metadata_max_bytes"] = srv.dagqlCacheMaxEstimatedBytes
		status["metadata_target_bytes"] = srv.dagqlCacheTargetEstimatedBytes
		if snapshotID != "" {
			_, err := srv.containerdMetaDB.Snapshotter(srv.snapshotterName).Stat(namespaces.WithNamespace(ctx, "dagger"), snapshotID)
			if err != nil && !cerrdefs.IsNotFound(err) {
				return nil, err
			}
			status["snapshot_exists"] = err == nil
		}
		return status, nil
	}
	srv.gcmu.Lock()
	defer srv.gcmu.Unlock()
	started := time.Now()
	ctx, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "gc.diagnostic."+action, wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	switch action {
	case "mode":
		srv.snapshotGarbage.deferred.Store(deferred)
		if drain {
			if err := srv.snapshotGarbage.collect(ctx); err != nil {
				return nil, err
			}
		}
		return srv.snapshotGarbage.diagnosticState(), nil
	case "collect":
		if err := srv.snapshotGarbage.collect(ctx); err != nil {
			return nil, err
		}
		return map[string]any{"seconds": time.Since(started).Seconds(), "started_at": started.UTC(), "ended_at": time.Now().UTC()}, nil
	case "account":
		result, err := srv.engineCache.MeasureUsageDiagnostic(ctx, false)
		if err != nil {
			return nil, err
		}
		result["started_at"] = started.UTC()
		result["ended_at"] = time.Now().UTC()
		return result, nil
	case "prepare":
		if !srv.snapshotGarbage.deferred.Load() {
			return nil, fmt.Errorf("defer ordinary collections before preparing scratch garbage")
		}
		if files < 0 || files > 100000 {
			return nil, fmt.Errorf("files must be between0 and100000")
		}
		owner, err := srv.leaseManager.Create(ctx, leases.WithRandomID(), bkcache.MakeTemporary)
		if err != nil {
			return nil, err
		}
		defer func() { rerr = errors.Join(rerr, srv.workerCache.RemoveLease(context.Background(), owner.ID)) }()
		ctx = leases.WithLease(ctx, owner.ID)
		mutable, err := srv.workerCache.New(ctx, nil)
		if err != nil {
			return nil, err
		}
		defer func() { rerr = errors.Join(rerr, mutable.Release(context.Background())) }()
		mounts, err := mutable.Mount(ctx, false)
		if err != nil {
			return nil, err
		}
		mounter := bkcache.LocalMounter(mounts)
		directory, err := mounter.Mount()
		if err != nil {
			return nil, err
		}
		mounted := true
		defer func() {
			if mounted {
				rerr = errors.Join(rerr, mounter.Unmount())
			}
		}()
		for i := 0; i < files; i++ {
			folder := filepath.Join(directory, fmt.Sprintf("group-%04d", i/100))
			if i%100 == 0 {
				if err := os.MkdirAll(folder, 0755); err != nil {
					return nil, err
				}
			}
			if err := os.WriteFile(filepath.Join(folder, fmt.Sprintf("file-%06d", i)), []byte("gc diagnostic\n"), 0644); err != nil {
				return nil, err
			}
		}
		if err := mounter.Unmount(); err != nil {
			return nil, err
		}
		mounted = false
		ref, err := mutable.Commit(ctx)
		if err != nil {
			return nil, err
		}
		if err := srv.workerCache.AttachLease(ctx, owner.ID, ref.SnapshotID()); err != nil {
			return nil, errors.Join(err, ref.Release(ctx))
		}
		id := ref.SnapshotID()
		if err := ref.Release(ctx); err != nil {
			return nil, err
		}
		return map[string]any{"snapshot_id": id, "files": files, "seconds": time.Since(started).Seconds()}, nil
	default:
		return nil, fmt.Errorf("unknown diagnostic action %q", action)
	}
}
