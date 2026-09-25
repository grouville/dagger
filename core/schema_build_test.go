package core

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/vektah/gqlparser/v2/ast"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
)

type artifactCoreForkTestMod struct {
	Mod
	base *dagql.Server
	view call.View
}

type artifactCoreForkTestServer struct {
	*preparationTestServer
	deps *SchemaBuilder
}

func (s *artifactCoreForkTestServer) DefaultDeps(context.Context) (*SchemaBuilder, error) {
	return s.deps, nil
}

func (*artifactCoreForkTestMod) Name() string              { return ModuleName }
func (m *artifactCoreForkTestMod) View() (call.View, bool) { return m.view, true }
func (*artifactCoreForkTestMod) Install(context.Context, *dagql.Server, ...InstallOpts) error {
	panic("artifact schemas must fork the prepared core")
}
func (m *artifactCoreForkTestMod) ForkSchema(ctx context.Context, root *Query, view call.View) (*dagql.Server, error) {
	srv, err := m.base.Fork(ctx, root)
	if err == nil {
		srv.View = view
	}
	return srv, err
}

// Discovery keeps the unversioned core API, but must rebuild caller-dependent
// module fields and keep them out of both the core template and other callers.
func TestArtifactSchemaForkViewAndIsolation(t *testing.T) {
	server := &artifactCoreForkTestServer{preparationTestServer: &preparationTestServer{mockServer: &mockServer{}}}
	root := &Query{Server: server}
	ctx := ContextWithQuery(t.Context(), root)
	base, err := dagql.NewServer(ctx, root)
	require.NoError(t, err)
	coreMod := &artifactCoreForkTestMod{base: base, view: "v0.21.0"}
	probe := &preparationTestMod{name: "probe"}
	mods := []modInstall{{mod: coreMod}, {mod: probe}}
	server.deps = NewSchemaBuilder(root, []Mod{coreMod, probe})
	base.InstallObject(dagql.NewClass(base, dagql.ClassOpts[*Module]{}))
	module := &Module{NameField: "fixture"}
	mod, err := dagql.NewObjectResultForCall(module, base, &dagql.ResultCall{
		Field: "fixture", Type: dagql.NewResultCallType(module.Type()),
	})
	require.NoError(t, err)
	var forks []*dagql.Server
	for _, caller := range []string{"first", "second"} {
		callerCtx := preparationContext(t, ctx, engine.NewClientScopeAuthority(), "session", caller, false)
		callerRoot := &Query{Server: root.Server}
		fork, err := dagqlServerForModule(ContextWithQuery(callerCtx, callerRoot), mod)
		require.NoError(t, err)
		require.Empty(t, fork.View, "artifact view must not inherit the authored module version")
		require.Same(t, callerRoot, fork.Root().Unwrap())
		field, exists := fork.Root().ObjectType().FieldSpec("probe", "")
		require.True(t, exists)
		require.Equal(t, caller, field.Description)
		forks = append(forks, fork)
	}
	// This also checks that the existing version-selecting path is unchanged.
	versioned, err := buildSchema(ctx, root, mods)
	require.NoError(t, err)
	require.Equal(t, call.View("v0.21.0"), versioned.View)
	require.EqualValues(t, 3, probe.installs.Load())
	_, exists := base.Root().ObjectType().FieldSpec("probe", "")
	require.False(t, exists, "module installation must not modify the core template")
	dagql.Fields[*Query]{dagql.Func("firstOnly", func(context.Context, *Query, struct{}) (string, error) {
		return "first", nil
	})}.Install(forks[0])
	_, exists = forks[1].Root().ObjectType().FieldSpec("firstOnly", "")
	require.False(t, exists)
}

func TestSchemaJSONFileSelectorHiddenFieldsAffectCallIdentity(t *testing.T) {
	hiddenTypes, hiddenFields := moduleIntrospectionScrubConfig()
	clientSelector := schemaJSONFileSelector("v1.0.0", nil, nil)
	moduleSelector := schemaJSONFileSelector("v1.0.0", hiddenTypes, hiddenFields)

	require.Equal(t, []string{
		"Query.currentWorkspace",
		"Query.engineVolume",
		"Query.sshfsVolume",
		"Address.volume",
	}, hiddenFields)
	require.Contains(t, hiddenTypes, "Host")
	require.NotEqual(t, selectorCallID(clientSelector).Digest(), selectorCallID(moduleSelector).Digest())

	hiddenFieldsInput, ok := dagql.Inputs(moduleSelector.Args).Lookup("hiddenFields")
	require.True(t, ok)
	require.Equal(t, `["Query.currentWorkspace","Query.engineVolume","Query.sshfsVolume","Address.volume"]`, hiddenFieldsInput.ToLiteral().Display())
}

func selectorCallID(selector dagql.Selector) *call.ID {
	args := make([]*call.Argument, 0, len(selector.Args))
	for _, arg := range selector.Args {
		args = append(args, call.NewArgument(arg.Name, arg.Value.ToLiteral(), false))
	}
	return call.New().Append(
		&ast.Type{NamedType: "File", NonNull: true},
		selector.Field,
		call.WithArgs(args...),
		call.WithView(selector.View),
	)
}
