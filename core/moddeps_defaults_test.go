package core

import (
	"context"
	"testing"

	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/engine"
	"github.com/dagger/dagger/internal/buildkit/session/secrets"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
)

type clientDefaultsTestServer struct {
	*moduleObjectTestServer
	memo *SchemaBuilderMemo
}

func (s *clientDefaultsTestServer) SessionSchemaBuilderMemo(context.Context) (*SchemaBuilderMemo, error) {
	return s.memo, nil
}

func (s *clientDefaultsTestServer) NonModuleParentClientMetadata(ctx context.Context) (*engine.ClientMetadata, error) {
	return engine.ClientMetadataFromContext(ctx)
}

func TestSchemaBuilderClientForksPreserveEnvironmentDefaults(t *testing.T) {
	f := newModuleOwnershipTest(t)
	server := &clientDefaultsTestServer{moduleObjectTestServer: f.root.Server.(*moduleObjectTestServer), memo: NewSchemaBuilderMemo()}
	f.root.Server = server
	server.attachables = map[string]*grpc.ClientConn{}
	for _, value := range []string{"A", "B"} {
		server.attachables[value] = newTestAttachableConn(t, func(s *grpc.Server) {
			secrets.RegisterSecretsServer(s, &testSecretsServer{data: []byte(value)})
		})
	}
	dagql.Fields[*FunctionArg]{dagql.Func("__withDefaultValue", func(_ context.Context, arg *FunctionArg, args struct{ DefaultValue JSON }) (*FunctionArg, error) {
		return arg.WithDefaultValue(args.DefaultValue), nil
	})}.Install(f.dag)
	mod := f.module(f.session("owner"), "probe", moduleOwnershipModuleOpts{
		userDefaults: NewEnvFile(true).WithVariable("CHECK_LABEL", "${CALLER_LABEL}"),
	})
	base := NewSchemaBuilder(f.root, []Mod{&artifactCoreForkTestMod{base: f.dag}, NewUserMod(mod)})
	// The same module must expose each caller's expanded default, even though
	// the callers share a session and the module's unexpanded .env contents.
	for _, value := range []string{"A", "B"} {
		root := &Query{Server: server}
		ctx := engine.ContextWithClientMetadata(dagql.ContextWithCache(t.Context(), f.cache), &engine.ClientMetadata{ClientID: value, SessionID: "same"})
		ctx = ContextWithQuery(ctx, root)
		dag, err := base.ForkForClient(root).Schema(ctx)
		require.NoError(t, err)
		obj, ok := dag.ObjectType("Probe")
		require.True(t, ok)
		spec, ok := obj.FieldSpec("check", "")
		require.True(t, ok)
		args := spec.Args.Inputs("")
		require.Len(t, args, 1)
		require.Equal(t, dagql.String(value), args[0].Default)
	}
}
