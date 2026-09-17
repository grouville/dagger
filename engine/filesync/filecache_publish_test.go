//go:build linux

package filesync

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"testing"
	"time"

	"github.com/containerd/containerd/v2/core/leases"
	"github.com/containerd/containerd/v2/core/mount"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	digest "github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
)

func TestFileCachePublisherReservationAndShutdown(t *testing.T) {
	t.Parallel()
	p := NewFileCachePublisher(nil, nil)
	require.True(t, p.reserve())
	require.False(t, p.reserve(), "busy admission must not queue")
	closed := make(chan struct{})
	go func() {
		p.Close()
		close(closed)
	}()
	<-p.ctx.Done()
	select {
	case <-closed:
		t.Fatal("Close returned before the reserved setup released ownership")
	default:
	}
	require.False(t, p.reserve(), "shutdown must reject new ownership setup")
	p.done()
	fileCachePublishTestWait(t, closed)
	p.Close()

	// Exercise the Add/Wait boundary under the race detector: either reserve
	// wins and Close waits for done, or Close wins and reserve declines.
	for range 100 {
		p := NewFileCachePublisher(nil, nil)
		start := make(chan struct{})
		var workers sync.WaitGroup
		workers.Add(2)
		go func() {
			defer workers.Done()
			<-start
			if p.reserve() {
				runtime.Gosched()
				p.done()
			}
		}()
		go func() {
			defer workers.Done()
			<-start
			p.Close()
		}()
		close(start)
		workers.Wait()
		require.False(t, p.reserve())
	}
}

func TestFileCachePublisherSkipsEmptyBusyAndClosed(t *testing.T) {
	t.Parallel()
	f := newFileCachePublishTestFixture(t)
	f.publisher.schedule(context.Background(), f.mirror, f.borrowed, f.originalRoot, &fileCacheCopy{})
	require.Zero(t, f.calls.count("lease.create"))
	require.True(t, f.publisher.reserve())
	f.publisher.schedule(context.Background(), f.mirror, f.borrowed, f.originalRoot, f.cache)
	require.Zero(t, f.calls.count("lease.create"))
	f.publisher.done()
	f.publisher.Close()
	f.publisher.schedule(context.Background(), f.mirror, f.borrowed, f.originalRoot, f.cache)
	require.Zero(t, f.calls.count("lease.create"))
}

func TestFileCachePublisherOwnsRemountedResultAfterRequestCancellation(t *testing.T) {
	t.Parallel()
	f := newFileCachePublishTestFixture(t)
	type requestKey struct{}
	requestCtx, cancelRequest := context.WithCancel(context.WithValue(context.Background(), requestKey{}, "request-only"))
	defer cancelRequest()
	entered := make(chan context.Context, 1)
	proceed := make(chan struct{})
	var unblock sync.Once
	releaseWorker := func() { unblock.Do(func() { close(proceed) }) }
	defer releaseWorker()
	f.owned.beforeMount = func(ctx context.Context) error {
		entered <- ctx
		select {
		case <-proceed:
			return context.Cause(ctx)
		case <-ctx.Done():
			return context.Cause(ctx)
		}
	}
	f.publisher.schedule(requestCtx, f.mirror, f.borrowed, f.originalRoot, f.cache)
	var workerCtx context.Context
	select {
	case workerCtx = <-entered:
	case <-time.After(5 * time.Second):
		t.Fatal("background admission did not reach its independent result mount")
	}
	cancelRequest()
	require.NoError(t, context.Cause(workerCtx), "request cancellation must not cancel the engine-owned job")
	require.Nil(t, workerCtx.Value(requestKey{}), "request values must not escape to the worker")
	require.Equal(t, 1, f.calls.count("attach:mirror"))
	require.Equal(t, 1, f.calls.count("attach:result"))
	require.Equal(t, 1, f.calls.count("get:result"))
	require.Zero(t, f.calls.count("borrowed.mount"))
	require.Zero(t, f.calls.count("owned.release"))
	require.Zero(t, f.calls.count("lease.remove"))
	_, err := os.Stat(f.cachePath())
	require.ErrorIs(t, err, os.ErrNotExist)

	// Commit may change the backing pathname. Admission must join relative
	// candidates to the owned immutable ref's current backing mount, not use
	// the old request path or the caller's ref.
	require.NoError(t, os.Rename(f.originalRoot, f.committedRoot))
	require.NoError(t, f.borrowed.Release(context.Background()))
	require.NoError(t, f.mirror.Release(context.Background()))
	releaseWorker()
	done := make(chan struct{})
	go func() { f.publisher.wg.Wait(); close(done) }()
	fileCachePublishTestWait(t, done)
	f.publisher.Close()

	resultPath := filepath.Join(f.committedRoot, "file")
	require.True(t, os.SameFile(fileCacheTestInfo(t, resultPath), fileCacheTestInfo(t, f.cachePath())))
	assertFileCacheContents(t, f.cachePath(), "finalized")
	require.Equal(t, 1, f.calls.count("owned.mount.readonly"))
	require.Equal(t, 1, f.calls.count("owned.release"))
	require.Equal(t, 1, f.calls.count("result-mount.release"))
	require.Equal(t, 1, f.calls.count("mirror-mount.release"))
	require.Equal(t, 1, f.calls.count("lease.remove"))
	require.Equal(t, 1, f.calls.count("borrowed.release"), "only the caller releases its ref")
	require.Equal(t, 1, f.calls.count("mirror.release"), "only the caller releases its mutable ref")
	require.Zero(t, f.calls.count("cleanup.canceled"))
	require.NoError(t, os.Remove(resultPath))
	assertFileCacheContents(t, f.cachePath(), "finalized")
}

func TestFileCachePublicationPrepareFailureCleansOwnership(t *testing.T) {
	t.Parallel()
	for _, name := range []string{
		"lease", "attach mirror", "attach result", "get result", "mirror mount", "mirror descriptor",
		"unsupported mount", "outside cache", "outside candidate", "root candidate",
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			f := newFileCachePublishTestFixture(t)
			wantErr := errors.New("injected failure")
			wantLease, wantResult, wantMount := 1, 0, 0
			switch name {
			case "lease":
				f.leases.createErr = wantErr
				wantLease = 0
			case "attach mirror":
				f.snapshots.attachErrID = "mirror"
			case "attach result":
				f.snapshots.attachErrID = "result"
			case "get result":
				f.snapshots.getErr = wantErr
			case "mirror mount":
				f.mirror.mountErr = wantErr
				wantResult = 1
			case "mirror descriptor":
				f.mirrorMount.err = wantErr
				wantResult, wantMount = 1, 1
			case "unsupported mount":
				f.mirrorMount.mounts[0].Options = []string{"uidmap=0:1000:1"}
				wantResult, wantMount = 1, 1
			case "outside cache":
				f.cache.root = t.TempDir()
				wantResult, wantMount = 1, 1
			case "outside candidate":
				f.cache.candidates[0].path = filepath.Join(t.TempDir(), "file")
				wantResult, wantMount = 1, 1
			case "root candidate":
				f.cache.candidates[0].path = f.originalRoot
				wantResult, wantMount = 1, 1
			}
			job, err := f.publisher.prepare(f.mirror, f.borrowed, f.originalRoot, f.cache)
			require.Error(t, err)
			require.Nil(t, job)
			require.Equal(t, wantLease, f.calls.count("lease.remove"))
			require.Equal(t, wantResult, f.calls.count("owned.release"))
			require.Equal(t, wantMount, f.calls.count("mirror-mount.release"))
			require.Zero(t, f.calls.count("borrowed.release"))
			require.Zero(t, f.calls.count("mirror.release"))
			require.Zero(t, f.calls.count("cleanup.canceled"))
		})
	}
}

func TestFileCachePublicationPublishFailureReleasesMount(t *testing.T) {
	t.Parallel()
	f := newFileCachePublishTestFixture(t)
	job, err := f.publisher.prepare(f.mirror, f.borrowed, f.originalRoot, f.cache)
	require.NoError(t, err)
	require.Equal(t, "file", job.candidates[0].path)
	require.Nil(t, job.candidates[0].stat, "jobs must not retain mirror change-cache stats")
	wantErr := errors.New("committed mount failed")
	f.resultMount.err = wantErr
	require.ErrorIs(t, job.publish(), wantErr)
	require.Equal(t, 1, f.calls.count("result-mount.release"))
	f.publisher.cancel()
	require.NoError(t, job.close())
	require.Equal(t, 1, f.calls.count("mirror-mount.release"))
	require.Equal(t, 1, f.calls.count("owned.release"))
	require.Equal(t, 1, f.calls.count("lease.remove"))
	require.Zero(t, f.calls.count("cleanup.canceled"), "cleanup must survive worker cancellation")
}

func TestFileCacheBindRootRejectsUnsupportedMounts(t *testing.T) {
	t.Parallel()
	root := t.TempDir()
	for name, mounts := range map[string][]mount.Mount{
		"none":     nil,
		"multiple": {{Type: "bind", Source: root}, {Type: "bind", Source: root}},
		"overlay":  {{Type: "overlay", Source: root}},
		"relative": {{Type: "bind", Source: "relative"}},
		"idmap":    {{Type: "bind", Source: root, Options: []string{"idmap"}}},
		"uidmap":   {{Type: "bind", Source: root, Options: []string{"uidmap=0:1000:1"}}},
		"gidmap":   {{Type: "bind", Source: root, Options: []string{"gidmap=0:1000:1"}}},
	} {
		t.Run(name, func(t *testing.T) { require.Empty(t, fileCacheBindRoot(mounts)) })
	}
	for _, kind := range []string{"bind", "rbind"} {
		require.Equal(t, root, fileCacheBindRoot([]mount.Mount{{Type: kind, Source: root, Options: []string{"ro", "rbind"}}}))
	}
}

type fileCachePublishTestCalls struct {
	mu     sync.Mutex
	counts map[string]int
}

func (c *fileCachePublishTestCalls) record(name string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.counts[name]++
}

func (c *fileCachePublishTestCalls) count(name string) int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.counts[name]
}

type fileCachePublishTestLeases struct {
	leases.Manager
	calls     *fileCachePublishTestCalls
	createErr error
}

func (l *fileCachePublishTestLeases) Create(ctx context.Context, opts ...leases.Opt) (leases.Lease, error) {
	l.calls.record("lease.create")
	if err := context.Cause(ctx); err != nil {
		return leases.Lease{}, err
	}
	if l.createErr != nil {
		return leases.Lease{}, l.createErr
	}
	var lease leases.Lease
	for _, opt := range opts {
		if err := opt(&lease); err != nil {
			return leases.Lease{}, err
		}
	}
	if lease.ID == "" || lease.Labels["containerd.io/gc.expire"] == "" || lease.Labels["buildkit/lease.temporary"] == "" {
		return leases.Lease{}, errors.New("missing independently owned expiring lease")
	}
	return lease, nil
}

type fileCachePublishTestSnapshots struct {
	bkcache.SnapshotManager
	calls       *fileCachePublishTestCalls
	result      bkcache.ImmutableRef
	attachErrID string
	getErr      error
}

func (s *fileCachePublishTestSnapshots) AttachLease(ctx context.Context, leaseID, snapshotID string) error {
	s.calls.record("attach:" + snapshotID)
	if err := context.Cause(ctx); err != nil {
		return err
	}
	if leaseID == "" || snapshotID == s.attachErrID {
		return errors.New("attach failed")
	}
	return nil
}

func (s *fileCachePublishTestSnapshots) RemoveLease(ctx context.Context, _ string) error {
	s.calls.record("lease.remove")
	if context.Cause(ctx) != nil {
		s.calls.record("cleanup.canceled")
	}
	return nil
}

func (s *fileCachePublishTestSnapshots) GetBySnapshotID(_ context.Context, id string, _ ...bkcache.RefOption) (bkcache.ImmutableRef, error) {
	s.calls.record("get:" + id)
	if s.getErr != nil {
		return nil, s.getErr
	}
	return s.result, nil
}

type fileCachePublishTestMount struct {
	name   string
	calls  *fileCachePublishTestCalls
	mounts []mount.Mount
	err    error
}

func (m *fileCachePublishTestMount) Mount() ([]mount.Mount, func() error, error) {
	return m.mounts, func() error { m.calls.record(m.name + ".release"); return nil }, m.err
}

type fileCachePublishTestImmutable struct {
	bkcache.ImmutableRef
	name        string
	calls       *fileCachePublishTestCalls
	mount       *fileCachePublishTestMount
	beforeMount func(context.Context) error
}

func (*fileCachePublishTestImmutable) SnapshotID() string { return "result" }
func (r *fileCachePublishTestImmutable) Mount(ctx context.Context, readonly bool) (bkcache.MountableRef, error) {
	r.calls.record(r.name + ".mount")
	if readonly {
		r.calls.record(r.name + ".mount.readonly")
	}
	if r.beforeMount != nil {
		if err := r.beforeMount(ctx); err != nil {
			return nil, err
		}
	}
	return r.mount, nil
}
func (r *fileCachePublishTestImmutable) Release(ctx context.Context) error {
	r.calls.record(r.name + ".release")
	if context.Cause(ctx) != nil {
		r.calls.record("cleanup.canceled")
	}
	return nil
}

type fileCachePublishTestMutable struct {
	bkcache.MutableRef
	calls    *fileCachePublishTestCalls
	mount    *fileCachePublishTestMount
	mountErr error
}

func (*fileCachePublishTestMutable) SnapshotID() string { return "mirror" }
func (r *fileCachePublishTestMutable) Mount(_ context.Context, readonly bool) (bkcache.MountableRef, error) {
	r.calls.record("mirror.mount")
	if readonly {
		return nil, errors.New("cache mount must be writable")
	}
	return r.mount, r.mountErr
}
func (r *fileCachePublishTestMutable) Release(context.Context) error {
	r.calls.record("mirror.release")
	return nil
}

type fileCachePublishTestFixture struct {
	publisher                   *FileCachePublisher
	calls                       *fileCachePublishTestCalls
	leases                      *fileCachePublishTestLeases
	snapshots                   *fileCachePublishTestSnapshots
	mirror                      *fileCachePublishTestMutable
	borrowed, owned             *fileCachePublishTestImmutable
	mirrorMount, resultMount    *fileCachePublishTestMount
	originalRoot, committedRoot string
	cache                       *fileCacheCopy
}

func newFileCachePublishTestFixture(t *testing.T) *fileCachePublishTestFixture {
	t.Helper()
	f := &fileCachePublishTestFixture{calls: &fileCachePublishTestCalls{counts: map[string]int{}}}
	base := t.TempDir()
	f.originalRoot, f.committedRoot = filepath.Join(base, "original"), filepath.Join(base, "committed")
	require.NoError(t, os.Mkdir(f.originalRoot, 0o755))
	file := filepath.Join(f.originalRoot, "file")
	require.NoError(t, os.WriteFile(file, []byte("finalized"), 0o640))
	mirrorRoot := filepath.Join(base, "mirror")
	cacheRoot := filepath.Join(mirrorRoot, "blobs")
	require.NoError(t, os.MkdirAll(cacheRoot, 0o700))
	f.mirrorMount = &fileCachePublishTestMount{name: "mirror-mount", calls: f.calls, mounts: []mount.Mount{{Type: "bind", Source: mirrorRoot}}}
	f.resultMount = &fileCachePublishTestMount{name: "result-mount", calls: f.calls, mounts: []mount.Mount{{Type: "bind", Source: f.committedRoot, Options: []string{"ro"}}}}
	f.mirror = &fileCachePublishTestMutable{calls: f.calls, mount: f.mirrorMount}
	f.borrowed = &fileCachePublishTestImmutable{name: "borrowed", calls: f.calls}
	f.owned = &fileCachePublishTestImmutable{name: "owned", calls: f.calls, mount: f.resultMount}
	f.leases = &fileCachePublishTestLeases{calls: f.calls}
	f.snapshots = &fileCachePublishTestSnapshots{calls: f.calls, result: f.owned}
	f.publisher = NewFileCachePublisher(f.snapshots, f.leases)
	t.Cleanup(f.publisher.Close)
	f.cache = &fileCacheCopy{root: cacheRoot, candidates: []fileCacheCandidate{{key: digest.FromString("finalized"), path: file, stat: &HashedStatInfo{}}}}
	return f
}

func (f *fileCachePublishTestFixture) cachePath() string {
	return fileCachePath(f.cache.root, f.cache.candidates[0].key)
}

func fileCachePublishTestWait(t *testing.T, done <-chan struct{}) {
	t.Helper()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("timed out waiting for publisher ownership cleanup")
	}
}
