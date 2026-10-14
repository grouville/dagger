package schema

import (
	"context"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	bkcache "github.com/dagger/dagger/engine/snapshots"
	"github.com/dagger/dagger/engine/snapshots/config"
	"github.com/dagger/dagger/engine/snapshots/testutil"
	"github.com/dagger/dagger/internal/buildkit/util/compression"
	"github.com/stretchr/testify/require"
)

func snapshotCheckpointSelector() dagql.Selector {
	return dagql.Selector{Field: "checkpoint", Args: []dagql.NamedInput{
		{Name: "snapshotIdentity", Value: dagql.NewBoolean(true)},
	}}
}

type checkpointReadObservedRef struct {
	bkcache.ImmutableRef
	mounts atomic.Int64
}

func (ref *checkpointReadObservedRef) Mount(ctx context.Context, readonly bool) (bkcache.MountableRef, error) {
	ref.mounts.Add(1)
	return ref.ImmutableRef.Mount(ctx, readonly)
}

func TestDirectorySnapshotCheckpointDoesNotReadContents(t *testing.T) {
	store := testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, store, "", "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := store.Build(t, nil, "value.txt", "immutable value")
	observed := &checkpointReadObservedRef{ImmutableRef: ref}
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", observed)
	var checkpoint dagql.ObjectResult[*core.Directory]
	require.NoError(t, srv.Select(ctx, producer, &checkpoint, snapshotCheckpointSelector()))
	call, err := checkpoint.ResultCall()
	require.NoError(t, err)
	require.Equal(t, "__checkpointDirectory", call.Field)
	// Checkpoint creation must not mount the contents to derive its identity.
	require.Zero(t, observed.mounts.Load())
	snapshot, ok := checkpoint.Self().Snapshot.Peek()
	require.True(t, ok)
	require.Equal(t, ref.SnapshotID(), snapshot.SnapshotID())
}

func TestDirectorySnapshotCheckpointSeparatesSnapshotsAndSubpaths(t *testing.T) {
	store := testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, store, "", "producer")
	installDirectoryCheckpoint(srv)
	first, _ := store.Build(t, nil, "a/value.txt", "first")
	second, _ := store.Build(t, nil, "a/value.txt", "second")
	shared, err := store.Manager.PinSnapshot(ctx, first.SnapshotID())
	require.NoError(t, err)
	sources := []dagql.ObjectResult[*core.Directory]{
		checkpointTestSource(t, ctx, cache, srv, "producer", "firstDirectory", first),
		checkpointTestSource(t, ctx, cache, srv, "producer", "sameSnapshotDirectory", shared),
		checkpointTestSource(t, ctx, cache, srv, "producer", "differentDirectory", second),
	}
	var results []dagql.ObjectResult[*core.Directory]
	for _, source := range sources {
		var checkpoint dagql.ObjectResult[*core.Directory]
		require.NoError(t, srv.Select(ctx, source, &checkpoint, snapshotCheckpointSelector()))
		results = append(results, checkpoint)
	}
	firstID, err := results[0].ID()
	require.NoError(t, err)
	sameID, err := results[1].ID()
	require.NoError(t, err)
	differentID, err := results[2].ID()
	require.NoError(t, err)
	require.Equal(t, firstID.EngineResultID(), sameID.EngineResultID())
	require.NotEqual(t, firstID.EngineResultID(), differentID.EngineResultID())
	// A view into the same snapshot is a distinct value when its path differs.
	view := &core.Directory{Platform: sources[0].Self().Platform,
		Dir: new(core.LazyAccessor[string, *core.Directory]), Snapshot: new(core.LazyAccessor[bkcache.ImmutableRef, *core.Directory])}
	view.SetPath("/a")
	viewRef, err := store.Manager.PinSnapshot(ctx, first.SnapshotID())
	require.NoError(t, err)
	view.SetSnapshot(viewRef)
	frame := &dagql.ResultCall{Kind: dagql.ResultCallKindField, Field: "subdirectoryView", Type: dagql.NewResultCallType(view.Type())}
	value, err := cache.GetOrInitCall(ctx, "producer", srv, &dagql.CallRequest{ResultCall: frame}, func(context.Context) (dagql.AnyResult, error) {
		return dagql.NewObjectResultForCall(view, srv, frame)
	})
	require.NoError(t, err)
	var selected dagql.ObjectResult[*core.Directory]
	require.NoError(t, srv.Select(ctx, value.(dagql.ObjectResult[*core.Directory]), &selected, snapshotCheckpointSelector()))
	selectedID, err := selected.ID()
	require.NoError(t, err)
	require.NotEqual(t, firstID.EngineResultID(), selectedID.EngineResultID())
}

func checkpointModes() []struct {
	name     string
	selector dagql.Selector
} {
	return []struct {
		name     string
		selector dagql.Selector
	}{
		{"content", dagql.Selector{Field: "checkpoint"}},
		{"snapshot", snapshotCheckpointSelector()},
	}
}

func checkpointTestSource(t *testing.T, ctx context.Context, cache *dagql.Cache, srv *dagql.Server, session, name string, ref bkcache.ImmutableRef) dagql.ObjectResult[*core.Directory] {
	t.Helper()
	dir := &core.Directory{Platform: core.Platform{OS: "linux", Architecture: "arm64"},
		Dir: new(core.LazyAccessor[string, *core.Directory]), Snapshot: new(core.LazyAccessor[bkcache.ImmutableRef, *core.Directory])}
	dir.SetPath("/")
	dir.SetSnapshot(ref)
	frame := &dagql.ResultCall{Kind: dagql.ResultCallKindField, Field: name, Type: dagql.NewResultCallType(dir.Type())}
	res, err := cache.GetOrInitCall(ctx, session, srv, &dagql.CallRequest{ResultCall: frame}, func(context.Context) (dagql.AnyResult, error) {
		return dagql.NewObjectResultForCall(dir, srv, frame)
	})
	require.NoError(t, err)
	return res.(dagql.ObjectResult[*core.Directory])
}

func TestDirectoryCheckpointOwnsSnapshotAfterProducerRelease(t *testing.T) {
	for _, mode := range checkpointModes() {
		t.Run(mode.name, func(t *testing.T) { testDirectoryCheckpointOwnsSnapshotAfterProducerRelease(t, mode.selector) })
	}
}

func testDirectoryCheckpointOwnsSnapshotAfterProducerRelease(t *testing.T, selector dagql.Selector) {
	t.Helper()
	store := testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, store, "", "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := store.Build(t, nil, "value.txt", "current value")
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", ref)
	producerID, err := producer.ID()
	require.NoError(t, err)
	var checkpoint dagql.ObjectResult[*core.Directory]
	require.NoError(t, srv.Select(ctx, producer, &checkpoint, selector))
	checkpointID, err := checkpoint.ID()
	require.NoError(t, err)
	require.NotEqual(t, producerID.EngineResultID(), checkpointID.EngineResultID())
	_, release, err := cache.HoldEntry(ctx, checkpointID.EngineResultID())
	require.NoError(t, err)
	require.NoError(t, cache.ReleaseSession(ctx, "producer"))
	_, unexpectedRelease, err := cache.HoldEntry(ctx, producerID.EngineResultID())
	if err == nil {
		require.NoError(t, unexpectedRelease(ctx))
	}
	require.ErrorIs(t, err, dagql.ErrUnknownEntry, "checkpoint must not retain producer history")
	store.GC(t)
	snapshot, ok := checkpoint.Self().Snapshot.Peek()
	require.True(t, ok)
	testutil.CheckFile(t, snapshot, "value.txt", "current value")
	record, err := cache.CapturePersistedRecord(ctx, checkpoint)
	require.NoError(t, err)
	require.Equal(t, "__checkpointDirectory", record.Call.Field)
	require.Nil(t, record.Call.Receiver)
	if len(selector.Args) == 0 {
		// The optional mode must preserve the existing persisted cache key.
		require.Len(t, record.Call.Args, 3)
		for _, arg := range record.Call.Args {
			require.NotEqual(t, "snapshot", arg.Name)
		}
	}
	require.NoError(t, release(ctx))
	_, err = cache.Prune(ctx, []dagql.CachePrunePolicy{{All: true}})
	require.NoError(t, err)
	_, unexpectedRelease, err = cache.HoldEntry(ctx, checkpointID.EngineResultID())
	if err == nil {
		require.NoError(t, unexpectedRelease(ctx))
	}
	require.ErrorIs(t, err, dagql.ErrUnknownEntry)
}

func TestDirectoryCheckpointSurvivesRestart(t *testing.T) {
	for _, mode := range checkpointModes() {
		t.Run(mode.name, func(t *testing.T) { testDirectoryCheckpointSurvivesRestart(t, mode.selector) })
	}
}

func testDirectoryCheckpointSurvivesRestart(t *testing.T, selector dagql.Selector) {
	t.Helper()
	store := testutil.NewStore(t)
	db := filepath.Join(t.TempDir(), "cache.db")
	ctx, cache, srv := scratchTestCache(t, store, db, "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := store.Build(t, nil, "value.txt", "saved value")
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", ref)
	var checkpoint dagql.ObjectResult[*core.Directory]
	require.NoError(t, srv.Select(ctx, producer, &checkpoint, selector))
	id, err := checkpoint.ID()
	require.NoError(t, err)
	require.NoError(t, cache.ReleaseSession(ctx, "producer"))
	require.NoError(t, cache.Close(ctx))
	store.Reload(t)
	ctx, cache, srv = scratchTestCache(t, store, db, "reader")
	installDirectoryCheckpoint(srv)
	loaded, err := cache.LoadResultByResultID(ctx, "reader", srv, id.EngineResultID())
	require.NoError(t, err)
	require.NoError(t, cache.Evaluate(ctx, loaded))
	snapshot, ok := loaded.Unwrap().(*core.Directory).Snapshot.Peek()
	require.True(t, ok)
	testutil.CheckFile(t, snapshot, "value.txt", "saved value")
	require.NoError(t, cache.ReleaseSession(ctx, "reader"))
}

func TestDirectoryCheckpointRefusesSessionResourceDependencies(t *testing.T) {
	for _, mode := range checkpointModes() {
		t.Run(mode.name, func(t *testing.T) { testDirectoryCheckpointRefusesSessionResourceDependencies(t, mode.selector) })
	}
}

func testDirectoryCheckpointRefusesSessionResourceDependencies(t *testing.T, selector dagql.Selector) {
	t.Helper()
	store := testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, store, "", "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := store.Build(t, nil, "value.txt", "guarded value")
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", ref)
	handle := dagql.SessionResourceHandle("checkpoint-secret")
	require.NoError(t, cache.BindSessionResource(ctx, "producer", "producer", handle, "bound"))
	frame := &dagql.ResultCall{Kind: dagql.ResultCallKindField, Field: "guard", Type: dagql.NewResultCallType(dagql.String("").Type())}
	guard, err := cache.GetOrInitCall(ctx, "producer", srv, &dagql.CallRequest{ResultCall: frame}, func(context.Context) (dagql.AnyResult, error) {
		value, err := dagql.NewResultForCall(dagql.String("guard"), frame)
		if err != nil {
			return nil, err
		}
		return value.WithSessionResourceHandle(ctx, handle)
	})
	require.NoError(t, err)
	require.NoError(t, cache.AddExplicitDependency(ctx, producer, guard, "guarded input"))
	var checkpoint dagql.ObjectResult[*core.Directory]
	err = srv.Select(ctx, producer, &checkpoint, selector)
	require.ErrorContains(t, err, "without session resources or services")
}

func TestDirectoryCheckpointTransfersWithoutProducerHistory(t *testing.T) {
	for _, mode := range checkpointModes() {
		t.Run(mode.name, func(t *testing.T) { testDirectoryCheckpointTransfersWithoutProducerHistory(t, mode.selector) })
	}
}

func testDirectoryCheckpointTransfersWithoutProducerHistory(t *testing.T, selector dagql.Selector) {
	t.Helper()
	aStore, bStore := testutil.NewStore(t), testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, aStore, "", "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := aStore.Build(t, nil, "value.txt", "transferred value")
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", ref)
	var checkpoint dagql.ObjectResult[*core.Directory]
	require.NoError(t, srv.Select(ctx, producer, &checkpoint, selector))
	reader, receiver, readerServer := scratchTestCache(t, bStore, "", "reader")
	installDirectoryCheckpoint(readerServer)
	err := cache.WithExportedValues(ctx, dagql.ValueSelection{
		Roots:   []dagql.AnyResult{checkpoint},
		Outputs: []dagql.SelectedValueOutput{{Result: checkpoint, Address: dagql.PersistedPartAddress{Part: "snapshot"}}},
	}, config.RefConfig{Compression: compression.New(compression.Uncompressed)}, func(ctx context.Context, exported *dagql.ExportedValues) error {
		require.Len(t, exported.Bundle.Values, 1, "only the closed snapshot value should transfer")
		require.Len(t, exported.Chains.Entries, 1)
		for _, entry := range exported.Chains.Entries {
			imported, err := bStore.Manager.ImportChain(ctx, &bkcache.ExportChain{Layers: entry.Layers, Provider: entry.Provider})
			require.NoError(t, err)
			defer imported.Release(context.WithoutCancel(ctx))
		}
		reply, err := receiver.MergeValues(reader, dagql.CloudCacheID, exported.Bundle)
		require.NoError(t, err)
		require.Len(t, reply.Imported(), 1)
		loaded, err := receiver.LoadResultByResultID(reader, "reader", readerServer, reply.Imported()[0].ResultID)
		require.NoError(t, err)
		require.NoError(t, receiver.Evaluate(reader, loaded))
		snapshot, ok := loaded.Unwrap().(*core.Directory).Snapshot.Peek()
		require.True(t, ok)
		testutil.CheckFile(t, snapshot, "value.txt", "transferred value")
		return nil
	})
	require.NoError(t, err)
}

type checkpointHookManager struct {
	bkcache.SnapshotManager
	afterPin func(context.Context)
}

func (m *checkpointHookManager) PinSnapshot(ctx context.Context, id string) (bkcache.ImmutableRef, error) {
	ref, err := m.SnapshotManager.PinSnapshot(ctx, id)
	if err == nil && m.afterPin != nil {
		m.afterPin(ctx)
	}
	return ref, err
}

func TestDirectoryCheckpointCancellationAfterPin(t *testing.T) {
	for _, mode := range checkpointModes() {
		t.Run(mode.name, func(t *testing.T) { testDirectoryCheckpointCancellationAfterPin(t, mode.selector) })
	}
}

func testDirectoryCheckpointCancellationAfterPin(t *testing.T, selector dagql.Selector) {
	t.Helper()
	store := testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, store, "", "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := store.Build(t, nil, "value.txt", "canceled value")
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", ref)
	canceled, cancel := context.WithCancel(ctx)
	manager := &checkpointHookManager{SnapshotManager: store.Manager, afterPin: func(context.Context) { cancel() }}
	srv.Root().(dagql.ObjectResult[*core.Query]).Self().Server.(*scratchTestServer).manager = manager
	var checkpoint dagql.ObjectResult[*core.Directory]
	err := srv.Select(canceled, producer, &checkpoint, selector)
	require.ErrorIs(t, err, context.Canceled)
	require.NoError(t, cache.ReleaseSession(ctx, "producer"))
	_, err = cache.Prune(ctx, []dagql.CachePrunePolicy{{All: true}})
	require.NoError(t, err)
	store.GC(t)
}

func TestDirectoryCheckpointConcurrentPublication(t *testing.T) {
	for _, mode := range checkpointModes() {
		t.Run(mode.name, func(t *testing.T) { testDirectoryCheckpointConcurrentPublication(t, mode.selector) })
	}
}

func testDirectoryCheckpointConcurrentPublication(t *testing.T, selector dagql.Selector) {
	t.Helper()
	store := testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, store, "", "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := store.Build(t, nil, "value.txt", "shared value")
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", ref)
	type answer struct {
		id  uint64
		err error
	}
	answers := make(chan answer, 8)
	start := make(chan struct{})
	var group sync.WaitGroup
	for range 8 {
		group.Go(func() {
			<-start
			var checkpoint dagql.ObjectResult[*core.Directory]
			err := srv.Select(ctx, producer, &checkpoint, selector)
			var number uint64
			if err == nil {
				id, idErr := checkpoint.ID()
				err = idErr
				if err == nil {
					number = id.EngineResultID()
				}
			}
			answers <- answer{number, err}
		})
	}
	close(start)
	group.Wait()
	close(answers)
	var expected uint64
	for got := range answers {
		require.NoError(t, got.err)
		if expected == 0 {
			expected = got.id
		}
		require.Equal(t, expected, got.id)
	}
	require.NoError(t, cache.ReleaseSession(ctx, "producer"))
	_, err := cache.Prune(ctx, []dagql.CachePrunePolicy{{All: true}})
	require.NoError(t, err)
	store.GC(t)
}

func TestDirectoryCheckpointRefusesResourceGrowthDuringPin(t *testing.T) {
	for _, mode := range checkpointModes() {
		t.Run(mode.name, func(t *testing.T) { testDirectoryCheckpointRefusesResourceGrowthDuringPin(t, mode.selector) })
	}
}

func testDirectoryCheckpointRefusesResourceGrowthDuringPin(t *testing.T, selector dagql.Selector) {
	t.Helper()
	store := testutil.NewStore(t)
	ctx, cache, srv := scratchTestCache(t, store, "", "producer")
	installDirectoryCheckpoint(srv)
	ref, _ := store.Build(t, nil, "value.txt", "guarded during copy")
	producer := checkpointTestSource(t, ctx, cache, srv, "producer", "producerDirectory", ref)
	handle := dagql.SessionResourceHandle("late-checkpoint-secret")
	require.NoError(t, cache.BindSessionResource(ctx, "producer", "producer", handle, "bound"))
	frame := &dagql.ResultCall{Kind: dagql.ResultCallKindField, Field: "guard", Type: dagql.NewResultCallType(dagql.String("").Type())}
	guard, err := cache.GetOrInitCall(ctx, "producer", srv, &dagql.CallRequest{ResultCall: frame}, func(context.Context) (dagql.AnyResult, error) {
		value, err := dagql.NewResultForCall(dagql.String("guard"), frame)
		if err != nil {
			return nil, err
		}
		return value.WithSessionResourceHandle(ctx, handle)
	})
	require.NoError(t, err)
	var once sync.Once
	manager := &checkpointHookManager{SnapshotManager: store.Manager, afterPin: func(context.Context) {
		once.Do(func() { require.NoError(t, cache.AddExplicitDependency(ctx, producer, guard, "late guarded input")) })
	}}
	srv.Root().(dagql.ObjectResult[*core.Query]).Self().Server.(*scratchTestServer).manager = manager
	var checkpoint dagql.ObjectResult[*core.Directory]
	err = srv.Select(ctx, producer, &checkpoint, selector)
	require.ErrorContains(t, err, "without session resources or services")
}
