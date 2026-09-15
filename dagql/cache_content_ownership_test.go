package dagql

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"slices"
	"sync"
	"testing"
	"time"

	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"
)

type persistContentValue struct {
	Root digest.Digest
	lazy LazyEvalFunc
}

func (*persistContentValue) Type() *ast.Type {
	return &ast.Type{NamedType: "PersistContentValue", NonNull: true}
}

func (v *persistContentValue) PersistedContentRefLinks() []PersistedContentRefLink {
	if v.Root == "" {
		return nil
	}
	return []PersistedContentRefLink{{Digest: v.Root, Role: "source"}}
}

func (v *persistContentValue) EncodePersistedObject(context.Context, PersistedObjectCache) (PersistedObjectEncoding, error) {
	payload, err := json.Marshal(v.Root)
	return PersistedObjectEncoding{JSON: payload, ContentLinks: v.PersistedContentRefLinks()}, err
}

func (*persistContentValue) DecodePersistedObject(_ context.Context, _ *Server, _ uint64, _ *ResultCall, payload json.RawMessage) (Typed, error) {
	v := &persistContentValue{}
	err := json.Unmarshal(payload, &v.Root)
	return v, err
}

func (*persistContentValue) OnRelease(context.Context) error { return nil }
func (v *persistContentValue) LazyEvalFunc() LazyEvalFunc    { return v.lazy }

// The real containerd graph/GC behavior is tested in engine/snapshots. This
// manager records the DagQL lifecycle boundaries and can fail a handoff without
// deleting any previously valid ownership.
type fakeContentManager struct {
	*fakeSnapshotManager
	mu         sync.Mutex
	owners     map[string]digest.Digest
	usage      map[digest.Digest][]bkcache.ContentUsage
	failAttach error
	events     []string
	onAttach   func()
}

func newFakeContentManager() *fakeContentManager {
	return &fakeContentManager{fakeSnapshotManager: &fakeSnapshotManager{},
		owners: make(map[string]digest.Digest), usage: make(map[digest.Digest][]bkcache.ContentUsage)}
}

func (*fakeContentManager) WithContentOperationLease(ctx context.Context, _ string) (context.Context, func(context.Context) error, error) {
	return withOperationLease(ctx)
}

func (m *fakeContentManager) AttachContentLease(_ context.Context, id string, root digest.Digest) error {
	if m.onAttach != nil {
		m.onAttach()
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, "attach:"+root.String())
	if m.failAttach != nil {
		return m.failAttach
	}
	m.owners[id] = root
	return nil
}

func (m *fakeContentManager) RemoveLease(_ context.Context, id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.events = append(m.events, "remove:"+m.owners[id].String())
	delete(m.owners, id)
	return nil
}

func (m *fakeContentManager) ContentUsage(_ context.Context, root digest.Digest) ([]bkcache.ContentUsage, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	usage, ok := m.usage[root]
	if !ok {
		return nil, fmt.Errorf("missing content %s", root)
	}
	return slices.Clone(usage), nil
}

func (m *fakeContentManager) hasOwner(root digest.Digest) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, owned := range m.owners {
		if owned == root {
			return true
		}
	}
	return false
}

func (m *fakeContentManager) DeleteStaleDaggerOwnerLeases(ctx context.Context, keep map[string]struct{}) error {
	if err := m.fakeSnapshotManager.DeleteStaleDaggerOwnerLeases(ctx, keep); err != nil {
		return err
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	for id := range m.owners {
		if _, retained := keep[id]; !retained {
			delete(m.owners, id)
		}
	}
	return nil
}

func contentTestResult(t *testing.T, ctx context.Context, c *Cache, session, field string, value *persistContentValue, persist bool) AnyResult {
	t.Helper()
	call := &ResultCall{Kind: ResultCallKindField, Type: NewResultCallType(value.Type()), Field: field}
	res, err := c.GetOrInitCall(ctx, session, noopTypeResolver{}, &CallRequest{ResultCall: call, IsPersistable: persist},
		func(context.Context) (AnyResult, error) { return cacheTestPlainResult(value), nil })
	require.NoError(t, err)
	return res
}

func TestCacheContentOwnerLeaseNormalization(t *testing.T) {
	a, b := digest.FromString("a"), digest.FromString("b")
	links := []PersistedContentRefLink{{b, "z"}, {a, "a"}, {a, "a"}}
	got, err := normalizeContentLinks(links)
	require.NoError(t, err)
	require.Equal(t, []PersistedContentRefLink{{a, "a"}, {b, "z"}}, got)
	require.Equal(t, "z", links[0].Role, "must not sort the provider's slice")
	for _, invalid := range [][]PersistedContentRefLink{{{a, ""}}, {{"bad", "a"}}, {{a, "a"}, {b, "a"}}} {
		_, err := normalizeContentLinks(invalid)
		require.Error(t, err)
	}
	require.NotEqual(t, resultSnapshotLeaseID(1, "content/source/"+a.String()), resultContentLeaseID(1, PersistedContentRefLink{a, "source"}))
}

func TestCacheContentOwnerReplacementAndRetry(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	m := newFakeContentManager()
	c, err := NewCache(ctx, "", m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	session := cacheTestSessionID(t, ctx)
	a, b := digest.FromString("a"), digest.FromString("b")
	value := &persistContentValue{Root: a}
	res := contentTestResult(t, ctx, c, session, "replace", value, false)
	attachErr := errors.New("transient content lookup failure")
	m.failAttach = attachErr
	require.ErrorIs(t, c.SyncResultSnapshotOwnerLeases(ctx, res), attachErr)
	require.True(t, m.hasOwner(a), "failed reattachment must preserve an existing owner")
	value.Root = b
	require.ErrorIs(t, c.SyncResultSnapshotOwnerLeases(ctx, res), attachErr)
	require.True(t, m.hasOwner(a), "failed replacement must preserve the old owner")
	require.True(t, res.cacheSharedResult().loadPayloadState().contentOwnerDirty)
	m.failAttach = nil
	m.events = nil
	require.NoError(t, c.SyncResultSnapshotOwnerLeases(ctx, res))
	require.Equal(t, []string{"attach:" + b.String(), "remove:" + a.String()}, m.events)
	require.False(t, res.cacheSharedResult().loadPayloadState().contentOwnerDirty)
	require.True(t, m.hasOwner(b))
	require.NoError(t, c.ReleaseSession(ctx, session))
	require.False(t, m.hasOwner(b))
}

func TestCacheContentOwnershipBeforeOperationRelease(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	m := newFakeContentManager()
	root := digest.FromString("published")
	released := make(chan bool, 1)
	ctx = ContextWithOperationLeaseProvider(ctx, OperationLeaseProviderFunc(func(ctx context.Context) (context.Context, func(context.Context) error, error) {
		return ctx, func(context.Context) error { released <- m.hasOwner(root); return nil }, nil
	}))
	c, err := NewCache(ctx, "", m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	contentTestResult(t, ctx, c, cacheTestSessionID(t, ctx), "publish", &persistContentValue{Root: root}, false)
	select {
	case owned := <-released:
		require.True(t, owned, "operation lease released before result ownership")
	case <-time.After(5 * time.Second):
		t.Fatal("operation lease was not released")
	}
}

func TestCacheContentOwnershipLazyHandoffFailure(t *testing.T) {
	for _, retry := range []bool{false, true} {
		t.Run(fmt.Sprintf("retry=%t", retry), func(t *testing.T) {
			ctx := cacheTestContext(t.Context())
			m := newFakeContentManager()
			root := digest.FromString("lazy-root")
			var mu sync.Mutex
			active := 0
			ctx = ContextWithOperationLeaseProvider(ctx, OperationLeaseProviderFunc(func(ctx context.Context) (context.Context, func(context.Context) error, error) {
				mu.Lock()
				active++
				mu.Unlock()
				return ctx, func(context.Context) error { mu.Lock(); active--; mu.Unlock(); return nil }, nil
			}))
			c, err := NewCache(ctx, "", m, nil)
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
			value := &persistContentValue{}
			bodyCalls := 0
			value.lazy = func(context.Context) error { bodyCalls++; value.Root = root; value.lazy = nil; return nil }
			session := cacheTestSessionID(t, ctx)
			res := contentTestResult(t, ctx, c, session, "lazy", value, false)
			m.failAttach = errors.New("handoff unavailable")
			require.ErrorContains(t, c.Evaluate(ctx, res), "handoff unavailable")
			mu.Lock()
			retained := active
			mu.Unlock()
			require.Equal(t, 1, retained, "consumed lazy work must keep its operation lease until handoff or abandonment")
			if retry {
				m.failAttach = nil
				require.NoError(t, c.Evaluate(ctx, res))
				require.True(t, m.hasOwner(root))
				mu.Lock()
				retained = active
				mu.Unlock()
				require.Zero(t, retained)
			}
			require.Equal(t, 1, bodyCalls, "bookkeeping retry must not replay the body")
			require.NoError(t, c.ReleaseSession(ctx, session))
			mu.Lock()
			retained = active
			mu.Unlock()
			require.Zero(t, retained, "abandoned result must release pending operation ownership")
		})
	}
}

func TestCacheContentOwnerLeaseSyncDefersSessionCleanup(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	m := newFakeContentManager()
	c, err := NewCache(ctx, "", m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	session := cacheTestSessionID(t, ctx)
	res := contentTestResult(t, ctx, c, session, "release-during-sync", &persistContentValue{Root: digest.FromString("a")}, false)
	started, resume := make(chan struct{}), make(chan struct{})
	m.onAttach = func() { close(started); <-resume }
	done := make(chan error, 1)
	go func() { done <- c.SyncResultSnapshotOwnerLeases(ctx, res) }()
	select {
	case <-started:
	case <-time.After(5 * time.Second):
		t.Fatal("attachment did not start")
	}
	require.NoError(t, c.ReleaseSession(ctx, session))
	require.Positive(t, c.Size())
	close(resume)
	require.NoError(t, <-done)
	require.Zero(t, c.Size())
}

func TestCacheContentPersistenceBeforeDecode(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	dbPath := filepath.Join(t.TempDir(), "cache.db")
	m := newFakeContentManager()
	c, err := NewCache(ctx, dbPath, m, nil)
	require.NoError(t, err)
	root, file := digest.FromString("tree"), digest.FromString("file")
	res := contentTestResult(t, ctx, c, "test-session", "persist-content", &persistContentValue{Root: root}, true)
	id := res.cacheSharedResult().id
	cacheTestReleaseSession(t, c, ctx)
	require.NoError(t, c.persistCurrentState(ctx))
	require.NoError(t, c.Close(context.Background()))
	m = newFakeContentManager()
	m.usage[root] = []bkcache.ContentUsage{{Digest: root, Size: 20}, {Digest: file, Size: 100}}
	c, err = NewCache(ctx, dbPath, m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	require.False(t, c.resultsByID[id].loadPayloadState().hasValue)
	require.True(t, m.hasOwner(root), "restore leases before payload decoding")
	require.Contains(t, m.deleteStaleKeep, resultContentLeaseID(id, PersistedContentRefLink{root, "source"}))
	entries := c.UsageEntriesAll(ctx)
	require.Len(t, entries, 1)
	require.EqualValues(t, 120, entries[0].SizeBytes)
	// An undecoded checkpoint must preserve the links too.
	require.NoError(t, c.persistCurrentState(ctx))
	rows, err := c.pdb.ListMirrorResultContentLinks(ctx)
	require.NoError(t, err)
	require.Len(t, rows, 1)
	report, err := c.Prune(ctx, []CachePrunePolicy{{All: true, MaxUsedSpace: 1, TargetSpace: 1}})
	require.NoError(t, err)
	require.EqualValues(t, 120, report.ReclaimedBytes)
	require.False(t, m.hasOwner(root))
	require.NoError(t, c.persistCurrentState(ctx))
	rows, err = c.pdb.ListMirrorResultContentLinks(ctx)
	require.NoError(t, err)
	require.Empty(t, rows)
}

func TestCacheContentSharedUsageAndLastOwner(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	m := newFakeContentManager()
	a, b, file := digest.FromString("a"), digest.FromString("b"), digest.FromString("shared")
	m.usage[a] = []bkcache.ContentUsage{{Digest: a, Size: 10}, {Digest: file, Size: 100}}
	m.usage[b] = []bkcache.ContentUsage{{Digest: b, Size: 20}, {Digest: file, Size: 100}}
	c, err := NewCache(ctx, "", m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	contentTestResult(t, ctx, c, "first", "a", &persistContentValue{Root: a}, true)
	contentTestResult(t, ctx, c, "second", "b", &persistContentValue{Root: b}, true)
	require.NoError(t, c.ReleaseSession(ctx, "first"))
	var total int64
	for _, entry := range c.UsageEntriesAll(ctx) {
		total += entry.SizeBytes
	}
	require.EqualValues(t, 130, total, "shared bytes must be charged once")
	policy := []CachePrunePolicy{{All: true, MaxUsedSpace: 1, TargetSpace: 1}}
	report, err := c.Prune(ctx, policy)
	require.NoError(t, err)
	require.EqualValues(t, 10, report.ReclaimedBytes, "live second owner retains the shared file")
	require.True(t, m.hasOwner(b))
	require.NoError(t, c.ReleaseSession(ctx, "second"))
	report, err = c.Prune(ctx, policy)
	require.NoError(t, err)
	require.EqualValues(t, 120, report.ReclaimedBytes)
}

func TestCacheContentPersistenceDecodePreservesCleanup(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	dbPath := filepath.Join(t.TempDir(), "cache.db")
	m := newFakeContentManager()
	c, err := NewCache(ctx, dbPath, m, nil)
	require.NoError(t, err)
	root := digest.FromString("decode-root")
	res := contentTestResult(t, ctx, c, "test-session", "decode", &persistContentValue{Root: root}, true)
	id := res.cacheSharedResult().id
	cacheTestReleaseSession(t, c, ctx)
	require.NoError(t, c.Close(context.Background()))
	m = newFakeContentManager()
	m.usage[root] = []bkcache.ContentUsage{{Digest: root, Size: 20}}
	c, err = NewCache(ctx, dbPath, m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	srv, err := NewServer(ctx, &persistCodecRoot{})
	require.NoError(t, err)
	srv.InstallObject(NewClass(srv, ClassOpts[*persistContentValue]{}))
	decoded, err := c.ensurePersistedHitValueLoaded(ContextWithCache(ctx, c), srv, Result[*persistContentValue]{shared: c.resultsByID[id]})
	require.NoError(t, err)
	require.Equal(t, root, decoded.Unwrap().(*persistContentValue).Root)
	_, err = c.Prune(ctx, []CachePrunePolicy{{All: true, MaxUsedSpace: 1, TargetSpace: 1}})
	require.NoError(t, err)
	require.False(t, m.hasOwner(root), "decoded OnReleaser must not replace content-lease cleanup")
}

func TestCacheContentPersistenceRequiresCompletedHandoff(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	m := newFakeContentManager()
	c, err := NewCache(ctx, "", m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	a, b := digest.FromString("before"), digest.FromString("after")
	value := &persistContentValue{Root: a}
	res := contentTestResult(t, ctx, c, cacheTestSessionID(t, ctx), "dirty", value, true)
	parent := contentTestResult(t, ctx, c, cacheTestSessionID(t, ctx), "dirty-parent", &persistContentValue{}, true)
	require.NoError(t, c.AddExplicitDependency(ctx, parent, res, "content test dependency"))
	value.Root = b
	_, err = c.snapshotPersistState(ctx)
	require.ErrorContains(t, err, "encoded content links differ from retained ownership")
	m.failAttach = errors.New("handoff unavailable")
	require.Error(t, c.SyncResultSnapshotOwnerLeases(ctx, res))
	snapshot, err := c.snapshotPersistState(ctx)
	require.NoError(t, err)
	require.Empty(t, snapshot.results, "partially attached roots must not be checkpointed")
	require.True(t, m.hasOwner(a))
	m.failAttach = nil
	require.NoError(t, c.SyncResultSnapshotOwnerLeases(ctx, res))
	snapshot, err = c.snapshotPersistState(ctx)
	require.NoError(t, err)
	require.Len(t, snapshot.results, 2)
	for _, result := range snapshot.results {
		if result.resultID == res.cacheSharedResult().id {
			require.Equal(t, b.String(), result.resultContentLinks[0].Digest)
		}
	}
}

func TestCacheContentEmptyCheckpointCleansOrphanedOperations(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	dbPath := filepath.Join(t.TempDir(), "cache.db")
	m := newFakeContentManager()
	c, err := NewCache(ctx, dbPath, m, nil)
	require.NoError(t, err)
	require.NoError(t, c.Close(context.Background()))
	root := digest.FromString("orphaned-lazy-output")
	m.owners["dagql/result/42/content-operation/orphan"] = root
	m.deleteStaleCallSeen = false
	c, err = NewCache(ctx, dbPath, m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	require.True(t, m.deleteStaleCallSeen, "even an empty checkpoint must reconcile ownership")
	require.Empty(t, m.deleteStaleKeep)
	require.False(t, m.hasOwner(root))
}

func TestCacheContentLazyOperationReleaseRetry(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	m := newFakeContentManager()
	var mu sync.Mutex
	active, failures := 0, 0
	ctx = ContextWithOperationLeaseProvider(ctx, OperationLeaseProviderFunc(func(ctx context.Context) (context.Context, func(context.Context) error, error) {
		mu.Lock()
		active++
		mu.Unlock()
		return ctx, func(context.Context) error {
			mu.Lock()
			defer mu.Unlock()
			if failures > 0 {
				failures--
				return errors.New("deletion unavailable")
			}
			active--
			return nil
		}, nil
	}))
	c, err := NewCache(ctx, "", m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	value := &persistContentValue{}
	root := digest.FromString("lazy-root")
	bodyCalls := 0
	value.lazy = func(context.Context) error {
		bodyCalls++
		value.Root = root
		value.lazy = nil
		mu.Lock()
		failures = 1
		mu.Unlock()
		return nil
	}
	res := contentTestResult(t, ctx, c, cacheTestSessionID(t, ctx), "release-retry", value, false)
	require.ErrorContains(t, c.Evaluate(ctx, res), "deletion unavailable")
	require.True(t, m.hasOwner(root), "permanent owner exists despite failed temporary-lease cleanup")
	require.NoError(t, c.Evaluate(ctx, res))
	require.Equal(t, 1, bodyCalls)
	mu.Lock()
	remaining := active
	mu.Unlock()
	require.Zero(t, remaining, "retry must release both old and current operation leases")
}

func TestCacheContentUsageRejectsMissingClosure(t *testing.T) {
	ctx := cacheTestContext(t.Context())
	m := newFakeContentManager()
	c, err := NewCache(ctx, "", m, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
	contentTestResult(t, ctx, c, "test-session", "missing", &persistContentValue{Root: digest.FromString("missing")}, true)
	cacheTestReleaseSession(t, c, ctx)
	_, err = c.Prune(ctx, []CachePrunePolicy{{All: true, MaxUsedSpace: 1, TargetSpace: 1}})
	require.ErrorContains(t, err, "missing content")
	require.Positive(t, c.Size(), "must not prune using an incomplete closure")
}

func TestCacheContentUsageRejectsChangedOwners(t *testing.T) {
	for _, mode := range []string{"add-before-publish", "add-after-publish", "remove-after-publish", "collect-after-publish"} {
		t.Run(mode, func(t *testing.T) {
			ctx := cacheTestContext(t.Context())
			m := newFakeContentManager()
			root := digest.FromString("shared-zero-byte-file")
			m.usage[root] = []bkcache.ContentUsage{{Digest: root, Size: 0}}
			c, err := NewCache(ctx, "", m, nil)
			require.NoError(t, err)
			t.Cleanup(func() { require.NoError(t, c.Close(context.Background())) })
			a, b := &persistContentValue{Root: root}, &persistContentValue{}
			if mode == "remove-after-publish" || mode == "collect-after-publish" {
				b.Root = root
			}
			first := contentTestResult(t, ctx, c, "first", "first", a, false)
			second := contentTestResult(t, ctx, c, "second", "second", b, false)
			inputs := c.collectUsageMeasurementInputs()
			require.NoError(t, expandContentUsageInputs(ctx, m, inputs))
			measurements := buildCacheUsageMeasurements(ctx, m, inputs)
			if mode == "add-before-publish" {
				b.Root = root
				require.NoError(t, c.syncResultContentLeases(ctx, second.cacheSharedResult()))
				require.ErrorContains(t, c.publishUsageMeasurements(measurements, inputs), "ownership changed")
				return
			}
			require.NoError(t, c.publishUsageMeasurements(measurements, inputs))
			_, err = c.snapshotPruneStateCancelable(nil, pruneSnapshotDisk, 0, nil)
			require.NoError(t, err, "a valid zero-byte measurement is not missing")
			switch mode {
			case "add-after-publish":
				b.Root = root
				require.NoError(t, c.syncResultContentLeases(ctx, second.cacheSharedResult()))
			case "remove-after-publish":
				a.Root = ""
				require.NoError(t, c.syncResultContentLeases(ctx, first.cacheSharedResult()))
			case "collect-after-publish":
				require.NoError(t, c.ReleaseSession(ctx, "first"))
			}
			_, err = c.snapshotPruneStateCancelable(nil, pruneSnapshotDisk, 0, nil)
			require.Error(t, err, "changed ownership requires a fresh accounting pass")
			require.NoError(t, c.measureAllResultSizes(ctx))
			_, err = c.snapshotPruneStateCancelable(nil, pruneSnapshotDisk, 0, nil)
			require.NoError(t, err)
		})
	}
}
