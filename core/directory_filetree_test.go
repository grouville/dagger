package core

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine/filetree"
	"github.com/opencontainers/go-digest"
	"github.com/stretchr/testify/require"
)

func TestDirectoryFileTreeEncodingKeepsAuthoritativeRoot(t *testing.T) {
	root := filetree.Object{Digest: digest.FromString("tree"), Size: 4}
	contentDigest := digest.FromString("semantic identity")
	dir := NewFileTreeDirectory(Platform{OS: "linux", Architecture: "amd64"}, root, contentDigest, "source-hint")
	require.True(t, dir.NeedsContentOperationLease())
	links := []dagql.PersistedContentRefLink{{Role: "filetree", Digest: root.Digest}}
	for _, materialized := range []bool{false, true} {
		if materialized {
			dir.Snapshot.SetValue(&cacheVolumeTestImmutableRef{snapshotID: "disposable-view"})
			dir.Lazy = nil
			require.Equal(t, []dagql.PersistedSnapshotRefLink{{Role: "snapshot", RefKey: "disposable-view"}}, dir.PersistedSnapshotRefLinks())
		} else {
			require.Empty(t, dir.PersistedSnapshotRefLinks())
		}
		encoded, err := dir.EncodePersistedObject(t.Context(), nil)
		require.NoError(t, err)
		require.Equal(t, links, encoded.ContentLinks)
		require.Empty(t, encoded.SnapshotLinks, "a derived view is not authoritative persisted state")
		var payload persistedDirectoryPayload
		require.NoError(t, json.Unmarshal(encoded.JSON, &payload))
		require.Equal(t, persistedDirectoryFormFileTree, payload.Form)
		require.Equal(t, root, payload.FileTree.Root)
		require.Equal(t, contentDigest, payload.FileTree.ContentDigest)
		require.Equal(t, "source-hint", payload.FileTree.SourceKey)
		if materialized {
			require.Equal(t, "disposable-view", payload.FileTree.ViewHint)
		}
	}
	dir.FileTree.Root.Digest = "invalid"
	_, err := dir.EncodePersistedObject(t.Context(), nil)
	require.Error(t, err)
}

type directoryNonContentTestLazy struct{}

func (*directoryNonContentTestLazy) Evaluate(_ context.Context, dir *Directory) error {
	dir.Dir.SetValue("evaluated")
	return nil
}

func (*directoryNonContentTestLazy) AttachDependencies(context.Context, func(dagql.AnyResult) (dagql.AnyResult, error)) ([]dagql.AnyResult, error) {
	return nil, nil
}

func (*directoryNonContentTestLazy) EncodePersisted(context.Context, dagql.PersistedObjectCache) (json.RawMessage, error) {
	return nil, errors.New("not a persistable test lazy")
}

func TestDirectoryWithoutFileTreeKeepsOrdinaryLazyLease(t *testing.T) {
	ctx := t.Context()
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.Close(context.Background())) })
	ctx = dagql.ContextWithCache(ctx, cache)
	srv := newCoreDagqlServerForTest(t, &Query{})
	srv.InstallObject(dagql.NewClass(srv, dagql.ClassOpts[*Directory]{}))
	dir := &Directory{Dir: new(LazyAccessor[string, *Directory]), Lazy: &directoryNonContentTestLazy{}}
	require.False(t, dir.NeedsContentOperationLease())
	call := &dagql.ResultCall{Kind: dagql.ResultCallKindSynthetic, SyntheticOp: "ordinary-lazy-directory", Type: dagql.NewResultCallType(dir.Type())}
	value, err := dagql.NewObjectResultForCall(dir, srv, call)
	require.NoError(t, err)
	result, err := cache.GetOrInitCall(ctx, "session", srv, &dagql.CallRequest{ResultCall: call}, dagql.ValueFunc(value))
	require.NoError(t, err)
	require.NoError(t, cache.Evaluate(ctx, result), "non-CAS Directory must not require a content manager")
	got, ok := dir.Dir.Peek()
	require.True(t, ok)
	require.Equal(t, "evaluated", got)
	require.Nil(t, dir.Lazy)
}
