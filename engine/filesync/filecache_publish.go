package filesync

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/mount"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/wcprof"
	"github.com/dagger/dagger/internal/buildkit/util/bklog"
)

// FileCachePublisher admits finalized result files to the optional inode cache.
// One engine-owned job may run at a time. A busy or closing publisher skips
// admission instead of delaying an import or retaining an unbounded backlog.
// Missing cache entries only cause a later import to copy those files again.
type FileCachePublisher struct {
	snapshots bkcache.SnapshotManager
	leases    leases.Manager
	ctx       context.Context
	cancel    context.CancelFunc
	mu        sync.Mutex
	active    bool
	closed    bool
	wg        sync.WaitGroup
}

func NewFileCachePublisher(snapshots bkcache.SnapshotManager, lm leases.Manager) *FileCachePublisher {
	ctx, cancel := context.WithCancel(context.Background())
	return &FileCachePublisher{snapshots: snapshots, leases: lm, ctx: ctx, cancel: cancel}
}

// Close stops admission and waits for all ownership cleanup, including setup
// racing with shutdown. Call it before closing the snapshot/lease managers.
func (p *FileCachePublisher) Close() {
	p.mu.Lock()
	p.closed = true
	p.cancel()
	p.mu.Unlock()
	p.wg.Wait()
}

func (p *FileCachePublisher) reserve() bool {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.closed || p.active {
		return false
	}
	p.active = true
	p.wg.Add(1)
	return true
}

func (p *FileCachePublisher) done() {
	p.mu.Lock()
	p.active = false
	p.mu.Unlock()
	p.wg.Done()
}

// schedule takes independent snapshot ownership before the import can return.
// It must be called only after the result is committed and all metadata writes
// have finished. Neither the request context nor its mounted paths escape.
func (p *FileCachePublisher) schedule(ctx context.Context, mirror bkcache.MutableRef, result bkcache.ImmutableRef, resultRoot string, cache *fileCacheCopy) {
	if len(cache.candidates) == 0 {
		return
	}
	if !p.reserve() {
		bklog.G(ctx).Debug("filesync file cache admission skipped: publisher busy or closed")
		return
	}
	_, op := wcprof.BeginOp(ctx, wcprof.OpKindIO, "filesync.filecache.handoff", wcprof.OpOpts{})
	job, err := p.prepare(mirror, result, resultRoot, cache)
	op.EndErr(err)
	if err != nil {
		p.done()
		bklog.G(ctx).WithError(err).Warn("filesync file cache admission skipped")
		return
	}
	if wcprof.Enabled(ctx) {
		// Preserve only the profiling opt-in, not the caller's span, current
		// operation, session values, or cancellation. Background work is a
		// separate root and must be accounted for outside the CLI interval.
		job.ctx = wcprof.ContextWithProfiling(job.ctx)
	}
	go func() {
		defer p.done()
		started := time.Now()
		var op *wcprof.Op
		job.ctx, op = wcprof.BeginOp(job.ctx, wcprof.OpKindIO, "filesync.filecache.background", wcprof.OpOpts{})
		err := job.publish()
		err = errors.Join(err, job.close())
		op.EndErr(err)
		// Engine-owned telemetry: do not retain a session tracer or extend its
		// shutdown barrier just to populate an optional cache.
		log := bklog.G(p.ctx).WithFields(map[string]any{
			"files": len(job.candidates), "duration": time.Since(started),
		})
		if err != nil {
			log.WithError(err).Warn("filesync file cache background admission failed")
		} else {
			log.Debug("filesync file cache background admission complete")
		}
	}()
}

type fileCachePublication struct {
	ctx          context.Context
	cancel       context.CancelFunc
	snapshots    bkcache.SnapshotManager
	leaseID      string
	result       bkcache.ImmutableRef
	cacheRelease func() error
	cacheRoot    string
	candidates   []fileCacheCandidate // keys and relative paths only; no mirror stats
}

func (p *FileCachePublisher) prepare(mirror bkcache.MutableRef, result bkcache.ImmutableRef, resultRoot string, cache *fileCacheCopy) (_ *fileCachePublication, rerr error) {
	ctx, cancel := context.WithTimeout(p.ctx, time.Minute)
	job := &fileCachePublication{ctx: ctx, cancel: cancel, snapshots: p.snapshots}
	defer func() {
		if rerr != nil {
			rerr = errors.Join(rerr, job.close())
		}
	}()
	// NewLease always creates a distinct lease (unlike WithLease). Its normal
	// one-hour expiration and temporary marker also bound retention after a
	// crash. The worker's deadline is shorter; cleanup runs after it stops.
	_, leaseCtx, err := bkcache.NewLease(ctx, p.leases, bkcache.MakeTemporary)
	if err != nil {
		return nil, err
	}
	job.leaseID, _ = leases.FromContext(leaseCtx)
	for _, ref := range []bkcache.Ref{mirror, result} {
		if err := p.snapshots.AttachLease(ctx, job.leaseID, ref.SnapshotID()); err != nil {
			return nil, err
		}
	}
	job.result, err = p.snapshots.GetBySnapshotID(ctx, result.SnapshotID(), bkcache.NoUpdateLastUsed)
	if err != nil {
		return nil, err
	}
	// A mutable ref cannot be acquired twice. Obtain an independent mount
	// descriptor while the caller still owns its mirror ref; the job's lease
	// protects the backing directory after that ref/runtime is released.
	mountable, err := mirror.Mount(ctx, false)
	if err != nil {
		return nil, err
	}
	mounts, release, err := mountable.Mount()
	job.cacheRelease = release
	if err != nil {
		return nil, err
	}
	root := fileCacheBindRoot(mounts)
	if root == "" {
		return nil, fmt.Errorf("unsupported file cache backing mount")
	}
	cachePath, err := filepath.Rel(root, cache.root)
	if err != nil || !filepath.IsLocal(cachePath) {
		return nil, fmt.Errorf("file cache is outside its owned snapshot")
	}
	job.cacheRoot = filepath.Join(root, cachePath)
	job.candidates = make([]fileCacheCandidate, 0, len(cache.candidates))
	for _, candidate := range cache.candidates {
		path, err := filepath.Rel(resultRoot, candidate.path)
		if err != nil || !filepath.IsLocal(path) || path == "." {
			return nil, fmt.Errorf("file cache candidate is outside its result")
		}
		job.candidates = append(job.candidates, fileCacheCandidate{key: candidate.key, path: path})
	}
	return job, nil
}

func (j *fileCachePublication) publish() (rerr error) {
	ctx, op := wcprof.BeginOp(j.ctx, wcprof.OpKindIO, "filesync.filecache.remountAndPublish", wcprof.OpOpts{})
	defer func() { op.EndErr(rerr) }()
	// The job is bounded to one minute; also bound its independent view lease.
	mountCtx := bkcache.WithMountLeaseExpiration(ctx, time.Hour)
	mountable, err := j.result.Mount(mountCtx, true)
	if err != nil {
		return err
	}
	mounts, release, err := mountable.Mount()
	if release != nil {
		defer func() { rerr = errors.Join(rerr, release()) }()
	}
	if err != nil {
		return err
	}
	root := fileCacheBindRoot(mounts)
	if root == "" {
		return fmt.Errorf("unsupported committed file cache source mount")
	}
	// Link backing files, not a read-only bind mount (which would introduce a
	// mount boundary). No byte or metadata writes are made through these paths.
	candidates := make([]fileCacheCandidate, 0, len(j.candidates))
	for _, candidate := range j.candidates {
		candidates = append(candidates, fileCacheCandidate{key: candidate.key, path: filepath.Join(root, candidate.path)})
	}
	cache := &fileCacheCopy{root: j.cacheRoot, candidates: candidates}
	return cache.publish(ctx)
}

func (j *fileCachePublication) close() (rerr error) {
	if j.cacheRelease != nil {
		rerr = errors.Join(rerr, j.cacheRelease())
	}
	if j.result != nil {
		rerr = errors.Join(rerr, j.result.Release(context.Background()))
	}
	if j.leaseID != "" {
		rerr = errors.Join(rerr, j.snapshots.RemoveLease(context.Background(), j.leaseID))
	}
	j.cancel()
	return rerr
}

// Flat result snapshots and the mirror use plain bind backing directories.
// Do not guess about layered or idmapped mounts.
func fileCacheBindRoot(mounts []mount.Mount) string {
	if len(mounts) != 1 || (mounts[0].Type != "bind" && mounts[0].Type != "rbind") || !filepath.IsAbs(mounts[0].Source) {
		return ""
	}
	for _, option := range mounts[0].Options {
		if strings.Contains(option, "idmap") || strings.HasPrefix(option, "uidmap=") || strings.HasPrefix(option, "gidmap=") {
			return ""
		}
	}
	return mounts[0].Source
}
