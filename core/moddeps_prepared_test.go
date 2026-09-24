package core

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

type preparationParentKey struct{}

func preparationContext(t *testing.T, ctx context.Context, authority *engine.ClientScopeAuthority, sessionID, clientID string, released bool) context.Context {
	t.Helper()
	md := &engine.ClientMetadata{SessionID: sessionID, ClientID: clientID}
	ctx = context.WithValue(ctx, preparationParentKey{}, md)
	if sessionID == "" || clientID == "" {
		return ctx
	}
	lease := engine.NewClientLifecycleLeaseWithDelegation(engine.ClientLeaseRequest, "test", nil, nil, nil, authority)
	t.Cleanup(lease.Release)
	scope, err := engine.NewClientScope(md, lease)
	require.NoError(t, err)
	ctx, err = engine.ContextWithClientScope(ctx, scope)
	require.NoError(t, err)
	if released {
		lease.Release()
	}
	return ctx
}

type preparationTestServer struct{ *mockServer }

func (*preparationTestServer) NonModuleParentClientMetadata(ctx context.Context) (*engine.ClientMetadata, error) {
	md, _ := ctx.Value(preparationParentKey{}).(*engine.ClientMetadata)
	return md, nil
}

type preparationTestMod struct {
	Mod
	name     string
	installs atomic.Int32
}

func (m *preparationTestMod) Name() string            { return m.name }
func (m *preparationTestMod) View() (call.View, bool) { return "", false }
func (m *preparationTestMod) Install(ctx context.Context, dag *dagql.Server, _ ...InstallOpts) error {
	m.installs.Add(1)
	parent := currentSchemaPreparationScope(ctx)
	dagql.Fields[*Query]{
		dagql.Func(m.name, func(_ context.Context, _ *Query, _ struct{}) (dagql.String, error) {
			return dagql.String(parent.clientID), nil
		}).Doc(parent.clientID),
	}.Install(dag)
	return nil
}

func TestPreparedSchemaForkScopeAndIsolation(t *testing.T) {
	for _, tc := range []struct {
		name       string
		sessionID  string
		clientID   string
		mutate     bool
		clone      bool
		entrypoint bool
		newSession bool
		unbound    bool
		released   bool
		wantReuse  bool
	}{
		{name: "same caller", sessionID: "session", clientID: "main", wantReuse: true},
		{name: "different caller", sessionID: "session", clientID: "exec"},
		{name: "different session", sessionID: "other", clientID: "main"},
		{name: "reused IDs in new session", sessionID: "session", clientID: "main", newSession: true},
		{name: "unbound scope", sessionID: "session", clientID: "main", unbound: true},
		{name: "released scope", sessionID: "session", clientID: "main", released: true},
		{name: "unknown caller"},
		{name: "module added", sessionID: "session", clientID: "main", mutate: true},
		{name: "ownership clone", sessionID: "session", clientID: "main", clone: true},
		{name: "entrypoint", sessionID: "session", clientID: "main", entrypoint: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			root := &Query{Server: &preparationTestServer{mockServer: &mockServer{}}}
			ctx := ContextWithQuery(t.Context(), root)
			authority := engine.NewClientScopeAuthority()
			baseCtx := preparationContext(t, ctx, authority, "session", "main", false)
			mod := &preparationTestMod{name: "probe"}
			base := NewSchemaBuilder(root, []Mod{mod})
			if tc.entrypoint {
				base = base.With(mod, InstallOpts{Entrypoint: true})
			}
			original, err := base.Schema(baseCtx)
			require.NoError(t, err)
			newRoot := &Query{Server: root.Server}
			child := base.WithRoot(newRoot)
			if tc.clone {
				child = child.Clone()
			}
			if tc.mutate {
				child = child.Append(&preparationTestMod{name: "extra"})
			}
			if tc.newSession {
				authority = engine.NewClientScopeAuthority()
			}
			if tc.unbound {
				authority = nil
			}
			childCtx := preparationContext(t, ctx, authority, tc.sessionID, tc.clientID, tc.released)
			forked, err := child.Schema(childCtx)
			require.NoError(t, err)
			wantInstalls := int32(2)
			if tc.wantReuse {
				wantInstalls = 1
			}
			if tc.entrypoint {
				wantInstalls *= 2 // each build has an inner and outer schema
			}
			require.Equal(t, wantInstalls, mod.installs.Load())
			require.NotSame(t, original, forked)
			require.Same(t, newRoot, forked.Root().Unwrap())
			field, ok := forked.Root().ObjectType().FieldSpec("probe", "")
			require.True(t, ok)
			require.Equal(t, currentSchemaPreparationScope(childCtx).clientID, field.Description)

			dagql.Fields[*Query]{dagql.Func("childOnly", func(_ context.Context, _ *Query, _ struct{}) (dagql.String, error) {
				return "child", nil
			})}.Install(forked)
			_, exists := original.Root().ObjectType().FieldSpec("childOnly", "")
			require.False(t, exists, "installing fields in a client must not mutate the prepared schema")
		})
	}
}

func TestPreparedSchemaConcurrentForks(t *testing.T) {
	root := &Query{Server: &preparationTestServer{mockServer: &mockServer{}}}
	ctx := preparationContext(t, ContextWithQuery(t.Context(), root), engine.NewClientScopeAuthority(), "session", "main", false)
	mod := &preparationTestMod{name: "probe"}
	base := NewSchemaBuilder(root, []Mod{mod})
	_, err := base.Schema(ctx)
	require.NoError(t, err)
	var wg sync.WaitGroup
	for range 16 {
		wg.Go(func() {
			_, err := base.WithRoot(&Query{Server: root.Server}).Schema(ctx)
			if err != nil {
				t.Error(err)
			}
		})
	}
	wg.Wait()
	require.EqualValues(t, 1, mod.installs.Load())
}
