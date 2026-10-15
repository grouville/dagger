package core

import (
	"context"
	"sync"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

// memoTestMod is a stand-in for a non-module Mod (like core), which the memo
// keys by instance.
type memoTestMod struct {
	Mod
	name string
}

func (m *memoTestMod) Name() string { return m.name }

func TestSchemaBuilderMemo(t *testing.T) {
	a, b := &memoTestMod{name: "a"}, &memoTestMod{name: "b"}
	root := &Query{}
	base := NewSchemaBuilder(root, []Mod{a})

	t.Run("same entries share a builder", func(t *testing.T) {
		memo := NewSchemaBuilderMemo()
		first := memo.Get(base.Clone().Append(b))
		require.Same(t, first, memo.Get(base.Clone().Append(b)))
		require.Same(t, first, memo.Get(base.Append(b)))
	})

	t.Run("different entries do not", func(t *testing.T) {
		memo := NewSchemaBuilderMemo()
		withB := memo.Get(base.Append(b))
		require.NotSame(t, withB, memo.Get(base.Clone()))
		require.NotSame(t, withB, memo.Get(base.Prepend(b)), "entry order is part of the key")
		require.NotSame(t, withB, memo.Get(base.Append(&memoTestMod{name: "b"})),
			"a different instance with the same name is a different module")
		require.NotSame(t, withB, memo.Get(base.With(b, InstallOpts{Entrypoint: true})),
			"install options are part of the key")
		require.NotSame(t, withB, memo.Get(base.WithRoot(&Query{}).Append(b)),
			"servers are built on the root, so it is part of the key")
	})

	t.Run("a failed build is not reused", func(t *testing.T) {
		memo := NewSchemaBuilderMemo()
		failed := memo.Get(base.Append(b))
		failed.loadSchemaFailed.Store(true)
		replaced := memo.Get(base.Append(b))
		require.NotSame(t, failed, replaced)
		require.Same(t, replaced, memo.Get(base.Append(b)))
	})

	t.Run("memos are independent", func(t *testing.T) {
		require.NotSame(t,
			NewSchemaBuilderMemo().Get(base.Append(b)),
			NewSchemaBuilderMemo().Get(base.Append(b)))
	})

	t.Run("a nil memo does not memoize", func(t *testing.T) {
		var memo *SchemaBuilderMemo
		deps := base.Append(b)
		require.Same(t, deps, memo.Get(deps))
	})
}

// ctxInstallMod installs nothing, failing only when the installing context is
// done.
type ctxInstallMod struct {
	Mod
}

func (*ctxInstallMod) Name() string            { return "ctx" }
func (*ctxInstallMod) View() (call.View, bool) { return "", false }
func (*ctxInstallMod) Install(ctx context.Context, _ *dagql.Server, _ ...InstallOpts) error {
	return ctx.Err()
}

// A shared builder must not hand one caller's cancellation to the others: the
// schema is fine, only that caller gave up.
func TestSchemaBuilderCanceledLoadDoesNotStick(t *testing.T) {
	deps := NewSchemaBuilderMemo().Get(NewSchemaBuilder(&Query{}, []Mod{&ctxInstallMod{}}))

	canceled, cancel := context.WithCancel(t.Context())
	cancel()
	_, err := deps.Schema(canceled)
	require.ErrorIs(t, err, context.Canceled)
	require.False(t, deps.loadSchemaFailed.Load(), "a canceled load is not a failed build")

	srv, err := deps.Schema(t.Context())
	require.NoError(t, err, "a later caller builds with its own context")
	again, err := deps.Schema(t.Context())
	require.NoError(t, err)
	require.Same(t, srv, again, "the built server is kept")
}

// memoTestServer hands out one session's schema builder memo, and a client
// memo of its own.
type memoTestServer struct {
	*mockServer
	client  *SchemaBuilderMemo
	session *SchemaBuilderMemo
}

func (s *memoTestServer) SchemaBuilderMemo(context.Context) (*SchemaBuilderMemo, error) {
	return s.client, nil
}

func (s *memoTestServer) SessionSchemaBuilderMemo(context.Context) (*SchemaBuilderMemo, error) {
	return s.session, nil
}

// A builder that is not client-owned, like a cached Module's Deps, never keeps
// the server it builds: the current session's memo does, so the server is
// built once per session, shared by its clients, and dies with it.
func TestSchemaBuilderServerLivesInSessionMemo(t *testing.T) {
	deps := NewSchemaBuilder(&Query{}, []Mod{&ctxInstallMod{}})
	session := NewSchemaBuilderMemo()
	client := func(session *SchemaBuilderMemo) context.Context {
		return ContextWithQuery(t.Context(), &Query{Server: &memoTestServer{mockServer: &mockServer{}, client: NewSchemaBuilderMemo(), session: session}})
	}

	srv, err := deps.Schema(client(session))
	require.NoError(t, err)
	again, err := deps.Schema(client(session))
	require.NoError(t, err)
	require.Same(t, srv, again, "the session's clients build the module set once")
	require.Nil(t, deps.lazilyLoadedServer, "the builder itself keeps no server")

	other, err := deps.Schema(client(NewSchemaBuilderMemo()))
	require.NoError(t, err)
	require.NotSame(t, srv, other, "another session builds its own")
}

type clientForkTestMod struct{ artifactProbeMod }

func (m *clientForkTestMod) Install(ctx context.Context, dag *dagql.Server, opts ...InstallOpts) error {
	if err := m.artifactProbeMod.Install(ctx, dag, opts...); err != nil {
		return err
	}
	dagql.Fields[*Query]{dagql.Func("marker", func(_ context.Context, root *Query, _ struct{}) (dagql.String, error) {
		return root.ConstructorArgs["marker"].(dagql.String), nil
	}).DoNotCache("Read this client's query root.")}.Install(dag)
	return nil
}

func TestSchemaBuilderClientForksShareInstallation(t *testing.T) {
	cache, err := dagql.NewCache(t.Context(), "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.Close(context.Background())) })
	ctx := dagql.ContextWithCache(t.Context(), cache)
	mod := &clientForkTestMod{}
	server := &memoTestServer{mockServer: &mockServer{}, session: NewSchemaBuilderMemo()}
	template := NewSchemaBuilder(&Query{Server: server}, []Mod{mod})
	const clients = 8
	var wg sync.WaitGroup
	var markers [clients]dagql.String
	var errs [clients]error
	for i := range clients {
		wg.Go(func() {
			root := &Query{Server: server, ConstructorArgs: map[string]dagql.Input{"marker": dagql.String(string(rune('a' + i)))}}
			ctx := ContextWithQuery(ctx, root)
			ctx = engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{ClientID: string(rune('a' + i)), SessionID: "forks"})
			fork, err := template.ForkForClient(root).Schema(ctx)
			if err != nil {
				errs[i] = err
				return
			}
			errs[i] = fork.Select(ctx, fork.Root(), &markers[i], dagql.Selector{Field: "marker"})
		})
	}
	wg.Wait()
	for i := range clients {
		require.NoError(t, errs[i])
		require.Equal(t, dagql.String(string(rune('a'+i))), markers[i])
	}
	require.Equal(t, 1, mod.installs, "the session installs the module set once")
	require.Nil(t, template.lazilyLoadedServer, "the cached module keeps no session server")
}

// With no session to hold it, the server is built for the one call.
func TestSchemaBuilderWithoutClientBuildsUncached(t *testing.T) {
	deps := NewSchemaBuilder(&Query{}, []Mod{&ctxInstallMod{}})
	srv, err := deps.Schema(t.Context())
	require.NoError(t, err)
	again, err := deps.Schema(t.Context())
	require.NoError(t, err)
	require.NotSame(t, srv, again)
	require.Nil(t, deps.lazilyLoadedServer)
}

// The memo owns a copy, never the caller's builder, and ownership is never
// inherited by a derived builder.
func TestSchemaBuilderMemoOwnsACopy(t *testing.T) {
	deps := NewSchemaBuilder(&Query{}, []Mod{&memoTestMod{name: "a"}})
	owned := NewSchemaBuilderMemo().Get(deps)
	require.NotSame(t, deps, owned)
	require.True(t, owned.clientOwned)
	require.False(t, deps.clientOwned)
	for name, derived := range map[string]*SchemaBuilder{
		"Clone":    owned.Clone(),
		"WithRoot": owned.WithRoot(&Query{}),
		"Append":   owned.Append(&memoTestMod{name: "b"}),
		"Prepend":  owned.Prepend(&memoTestMod{name: "b"}),
		"With":     owned.With(&memoTestMod{name: "b"}, InstallOpts{}),
	} {
		require.False(t, derived.clientOwned, name)
	}
}
