package schema

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/dagger/dagger/engine"
	"github.com/stretchr/testify/require"
)

func cliJSONHarness(t *testing.T, view call.View) (context.Context, *dagql.Server) {
	t.Helper()
	ctx := t.Context()
	cache, err := dagql.NewCache(ctx, "", nil, nil)
	require.NoError(t, err)
	t.Cleanup(func() { require.NoError(t, cache.Close(context.Background())) })
	ctx = dagql.ContextWithCache(ctx, cache)
	ctx = engine.ContextWithClientMetadata(ctx, &engine.ClientMetadata{ClientID: "cli-json-client", SessionID: "cli-json-session"})
	server := &currentTypeDefsTestServer{}
	root := core.NewRoot(server)
	ctx = core.ContextWithQuery(ctx, root)
	base, err := NewCoreSchemaBase(ctx, server)
	require.NoError(t, err)
	dag, err := base.Fork(ctx, root, view)
	require.NoError(t, err)
	server.deps = core.NewSchemaBuilder(root, []core.Mod{base.CoreMod(view)})
	server.dag = dag
	return ctx, dag
}

func cliOriginalQuery(t *testing.T) string {
	t.Helper()
	source, err := os.ReadFile("../../internal/cmd/dagger/typedefs.graphql")
	require.NoError(t, err)
	return string(source)
}

func assertCLIJSON(t *testing.T, old, compact map[string]any) {
	t.Helper()
	want, err := json.Marshal(old["typeDefs"])
	require.NoError(t, err)
	encoded, err := json.Marshal(compact["typeDefs"])
	require.NoError(t, err)
	var got string
	require.NoError(t, json.Unmarshal(encoded, &got))
	require.JSONEq(t, string(want), got)
}

func TestCLITypeDefsJSONCoreParity(t *testing.T) {
	for _, view := range []call.View{"v0.21.5", "v1.0.0"} {
		t.Run(string(view), func(t *testing.T) {
			ctx, dag := cliJSONHarness(t, view)
			for _, hide := range []bool{false, true} {
				old, err := dag.Query(ctx, cliOriginalQuery(t), map[string]any{"hideCore": hide})
				require.NoError(t, err)
				compact, err := dag.Query(ctx, `query($hideCore: Boolean) { typeDefs: __currentTypeDefsJSON(returnAllTypes: true, hideCore: $hideCore) }`, map[string]any{"hideCore": hide})
				require.NoError(t, err)
				assertCLIJSON(t, old, compact)
			}
		})
	}
}

func cliFixtureType(t *testing.T, ctx context.Context, dag *dagql.Server, selectors ...dagql.Selector) dagql.ObjectResult[*core.TypeDef] {
	t.Helper()
	var td dagql.ObjectResult[*core.TypeDef]
	err := dag.Select(ctx, dag.Root(), &td, append([]dagql.Selector{{Field: "typeDef"}}, selectors...)...)
	require.NoError(t, err)
	return td
}

func cliFixtureID[T dagql.Typed](t *testing.T, result dagql.ObjectResult[T]) dagql.ID[T] {
	t.Helper()
	id, err := result.ID()
	require.NoError(t, err)
	return dagql.NewID[T](id)
}

func cliFixtureDefs(t *testing.T, ctx context.Context, dag *dagql.Server) dagql.ObjectResultArray[*core.TypeDef] {
	t.Helper()
	str := cliFixtureType(t, ctx, dag, dagql.Selector{Field: "withKind", Args: []dagql.NamedInput{{Name: "kind", Value: core.TypeDefKindString}}})
	directory := cliFixtureType(t, ctx, dag, dagql.Selector{Field: "withObject", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("Directory")}}})
	check := cliFixtureType(t, ctx, dag, dagql.Selector{Field: "withObject", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("Check")}}})
	keys := cliFixtureType(t, ctx, dag, dagql.Selector{Field: "withListOf", Args: []dagql.NamedInput{{Name: "elementType", Value: cliFixtureID(t, str)}}})
	var function dagql.ObjectResult[*core.Function]
	require.NoError(t, dag.Select(ctx, dag.Root(), &function,
		dagql.Selector{Field: "__function", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("readExact")}, {Name: "returnType", Value: cliFixtureID(t, str)}, {Name: "sourceModuleName", Value: dagql.Opt(dagql.String("FixtureOwner"))}}},
		dagql.Selector{Field: "withDescription", Args: []dagql.NamedInput{{Name: "description", Value: dagql.String("Documented function\nwith details.")}}},
		dagql.Selector{Field: "withArg", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("source")}, {Name: "typeDef", Value: cliFixtureID(t, directory)}, {Name: "defaultPath", Value: dagql.String(".")}, {Name: "ignore", Value: dagql.ArrayInput[dagql.String]{"**/.git", "!keep"}}}},
		dagql.Selector{Field: "withArg", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("message")}, {Name: "typeDef", Value: cliFixtureID(t, str)}, {Name: "defaultValue", Value: core.JSON(`"hello"`)}}},
	))
	// Publish a legacy check-shaped function through the ordinary ownership
	// machinery; its two return types intentionally differ.
	dagql.Fields[*core.Query]{dagql.Func("cliFixtureCheck", func(context.Context, *core.Query, struct{}) (*core.Function, error) {
		return &core.Function{Name: "verify", OriginalName: "verify", ReturnType: check, CheckReturnType: str, IsCheck: true, SourceModuleName: "FixtureOwner"}, nil
	})}.Install(dag)
	var checked dagql.ObjectResult[*core.Function]
	require.NoError(t, dag.Select(ctx, dag.Root(), &checked, dagql.Selector{Field: "cliFixtureCheck"}))
	obj := cliFixtureType(t, ctx, dag,
		dagql.Selector{Field: "withObject", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("FixtureThing")}, {Name: "sourceModuleName", Value: dagql.Opt(dagql.String("FixtureOwner"))}, {Name: "description", Value: dagql.String("Object docs")}}},
		dagql.Selector{Field: "withFunction", Args: []dagql.NamedInput{{Name: "function", Value: cliFixtureID(t, function)}}},
		dagql.Selector{Field: "withFunction", Args: []dagql.NamedInput{{Name: "function", Value: cliFixtureID(t, checked)}}},
		dagql.Selector{Field: "withConstructor", Args: []dagql.NamedInput{{Name: "function", Value: cliFixtureID(t, function)}}},
	)
	if !AfterVersion("v1.0.0-0").Contains(dag.View) {
		return dagql.ObjectResultArray[*core.TypeDef]{str, keys, directory, check, obj}
	}
	var get dagql.ObjectResult[*core.Function]
	require.NoError(t, dag.Select(ctx, dag.Root(), &get,
		dagql.Selector{Field: "function", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("lookup")}, {Name: "returnType", Value: cliFixtureID(t, obj)}}},
		dagql.Selector{Field: "withArg", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("name")}, {Name: "typeDef", Value: cliFixtureID(t, str)}}},
	))
	collection := cliFixtureType(t, ctx, dag,
		dagql.Selector{Field: "withObject", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("FixtureItems")}, {Name: "sourceModuleName", Value: dagql.Opt(dagql.String("OtherOwner"))}}},
		dagql.Selector{Field: "withCollection"},
		dagql.Selector{Field: "withCollectionKeys", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("names")}}},
		dagql.Selector{Field: "withCollectionGet", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("lookup")}}},
		dagql.Selector{Field: "withField", Args: []dagql.NamedInput{{Name: "name", Value: dagql.String("names")}, {Name: "typeDef", Value: cliFixtureID(t, keys)}}},
		dagql.Selector{Field: "withFunction", Args: []dagql.NamedInput{{Name: "function", Value: cliFixtureID(t, get)}}},
		dagql.Selector{Field: "withFunction", Args: []dagql.NamedInput{{Name: "function", Value: cliFixtureID(t, function)}}},
	)
	return dagql.ObjectResultArray[*core.TypeDef]{str, keys, directory, check, obj, collection}
}

func TestCLITypeDefsJSONAdaptersAndDefaults(t *testing.T) {
	for _, view := range []call.View{"v0.21.5", "v1.0.0"} {
		t.Run(string(view), func(t *testing.T) {
			ctx, dag := cliJSONHarness(t, view)
			defs := cliFixtureDefs(t, ctx, dag)
			s := &moduleSchema{}
			dagql.Fields[*core.Query]{
				dagql.Func("cliFixtureDefs", func(context.Context, *core.Query, struct{}) (dagql.ObjectResultArray[*core.TypeDef], error) {
					return defs, nil
				}),
				dagql.Func("cliFixtureJSON", func(ctx context.Context, _ *core.Query, _ struct{}) (core.JSON, error) {
					return s.projectCLITypeDefs(ctx, defs)
				}).View(AllVersion),
			}.Install(dag)
			query := strings.Replace(cliOriginalQuery(t), "query TypeDefs($hideCore: Boolean)", "query TypeDefs", 1)
			query = strings.Replace(query, "currentTypeDefs(returnAllTypes: true, hideCore: $hideCore)", "cliFixtureDefs", 1)
			old, err := dag.Query(ctx, query, nil)
			require.NoError(t, err)
			compact, err := dag.Query(ctx, `{ typeDefs: cliFixtureJSON }`, nil)
			require.NoError(t, err)
			assertCLIJSON(t, old, compact)

			// Repeat through the production endpoint and current schema input,
			// not merely the projector's test wrapper. The embedded CoreMod
			// supplies normal schema installation, with these held definitions
			// representing metadata contributed by a module.
			root, err := core.CurrentQuery(ctx)
			require.NoError(t, err)
			server := root.Server.(*currentTypeDefsTestServer)
			installed := server.deps.Mods()[0].(*CoreMod)
			server.deps = core.NewSchemaBuilder(root, []core.Mod{&cliMetadataFixtureMod{CoreMod: installed, defs: defs}})
			old, err = dag.Query(ctx, cliOriginalQuery(t), map[string]any{"hideCore": false})
			require.NoError(t, err)
			compact, err = dag.Query(ctx, `{ typeDefs: __currentTypeDefsJSON(returnAllTypes: true, hideCore: false) }`, nil)
			require.NoError(t, err)
			assertCLIJSON(t, old, compact)
		})
	}
}

type cliMetadataFixtureMod struct {
	*CoreMod
	defs dagql.ObjectResultArray[*core.TypeDef]
}

func (m *cliMetadataFixtureMod) TypeDefs(context.Context, *dagql.Server) (dagql.ObjectResultArray[*core.TypeDef], error) {
	return m.defs, nil
}

func TestCLITypeDefsJSONErrorsAndCancellation(t *testing.T) {
	s := &moduleSchema{}
	_, err := s.projectCLITypeDefs(t.Context(), dagql.ObjectResultArray[*core.TypeDef]{{}})
	require.ErrorContains(t, err, "nil TypeDef")
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	_, err = s.projectCLITypeDefs(ctx, dagql.ObjectResultArray[*core.TypeDef]{{}})
	require.ErrorIs(t, err, context.Canceled)
}
