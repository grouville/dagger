package dangv2

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/Khan/genqlient/graphql"
	"github.com/dagger/dagger/dagql/call"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vito/dang/v2/pkg/dang"
	"github.com/vito/dang/v2/pkg/hm"
)

func TestReusableDeclarationsHandleIdentities(t *testing.T) {
	typ := call.NewType(&ast.Type{NamedType: "File", NonNull: true})
	source := call.NewEngineResultID(42, typ)
	schema := call.NewEngineResultID(43, typ)
	key, err := newDeclarationKey(source, schema, "/source")
	if err != nil {
		t.Fatal(err)
	}
	again, err := newDeclarationKey(source, schema, "/source")
	if err != nil || again != key {
		t.Fatalf("identity is unstable: %v", err)
	}
	changed := call.NewEngineResultID(44, typ)
	for _, pair := range [][2]*call.ID{{changed, schema}, {source, changed}} {
		other, err := newDeclarationKey(pair[0], pair[1], "/source")
		if err != nil || other == key {
			t.Fatalf("different results have the same key: %v", err)
		}
	}
	if _, err := newDeclarationKey(nil, schema, "/source"); err == nil {
		t.Fatal("missing identity accepted")
	}
}

type declarationObjectClient string

func (client declarationObjectClient) MakeRequest(_ context.Context, _ *graphql.Request, response *graphql.Response) error {
	data, err := json.Marshal(map[string]any{"container": map[string]string{"id": string(client)}})
	if err != nil {
		return err
	}
	return json.Unmarshal(data, response.Data)
}

func TestReusableDeclarationsBindsLazyGraphQLValues(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "main.dang"), []byte("type Demo { result: Dagger.Container! { container } }"), 0600); err != nil {
		t.Fatal(err)
	}
	schema, err := dang.SchemaFromSDL("type Query { container: Container! } type Container { id: ID! }", "schema.graphqls")
	if err != nil {
		t.Fatal(err)
	}
	key := declarationKey{source: "lazy-output", schema: "container", directory: dir}
	run := func(ctx context.Context, dir string) (dang.ValueScope, error) { return dang.RunDir(ctx, dir, false) }
	for _, name := range []string{"first-client", "second-client"} {
		ctx := context.WithValue(t.Context(), invocationClientKey{}, declarationObjectClient(name))
		ctx = dang.ContextWithImportConfigs(ctx, dang.ImportConfig{Name: "Dagger", Client: invocationClient{}, Schema: schema, AutoImport: true})
		env, err := loadDeclarationTest(ctx, key, run)
		if err != nil {
			t.Fatal(err)
		}
		constructor, _, err := env.Lookup(ctx, "Demo")
		if err != nil {
			t.Fatal(err)
		}
		object, err := constructor.(*dang.ConstructorFunction).Call(ctx, env, nil)
		if err != nil {
			t.Fatal(err)
		}
		value, err := dang.EvalNode(ctx, env, &dang.FunCall{Fun: &dang.Select{Receiver: &dang.ValueNode{Val: object}, Field: &dang.Symbol{Name: "result"}}})
		if err != nil {
			t.Fatal(err)
		}
		// Standard JSON marshaling has no Go context. The value must already
		// carry this invocation's client, rather than its prepared code's proxy.
		encoded, err := json.Marshal(value)
		want, _ := json.Marshal(name)
		if err != nil || string(encoded) != string(want) {
			t.Fatalf("lazy ID serialization: %s: %v", encoded, err)
		}
	}
}

func TestKnownInputIDDoesNotQueryForItself(t *testing.T) {
	schema, err := dang.SchemaFromSDL("type Query { node(id: ID!): Node } interface Node { id: ID! } type Container implements Node { id: ID! }", "schema.graphqls")
	if err != nil {
		t.Fatal(err)
	}
	types := dang.TypeScopeFromSchema("Dagger", schema)
	env := dang.ValueScopeFromSchema(types, nil, schema)
	container, ok := types.NamedType("Container")
	if !ok {
		t.Fatal("missing Container")
	}
	converter := dangConverter{env: env}
	saved := knownInputIDsEnabled.Load()
	knownInputIDsEnabled.Store(true)
	t.Cleanup(func() { knownInputIDsEnabled.Store(saved) })
	value, err := converter.convertObjectID(t.Context(), "already-known-id", container.(*dang.Type))
	if err != nil {
		t.Fatal(err)
	}
	gql := value.(dang.GraphQLValue)
	if gql.Type().(hm.NonNullType).Type != container {
		t.Fatal("converted type changed")
	}
	data, err := json.Marshal(gql)
	if err != nil || string(data) != `"already-known-id"` {
		t.Fatalf("known ID was queried or changed: %s: %v", data, err)
	}
}

type declarationTestClient string

func (client declarationTestClient) MakeRequest(ctx context.Context, _ *graphql.Request, response *graphql.Response) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	data, err := json.Marshal(map[string]string{"value": string(client)})
	if err != nil {
		return err
	}
	return json.Unmarshal(data, response.Data)
}

func declarationTestContext(t *testing.T, name, schemaSource string) context.Context {
	t.Helper()
	schema, err := dang.SchemaFromSDL(schemaSource, "schema.graphqls")
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.WithValue(t.Context(), invocationClientKey{}, declarationTestClient(name))
	return dang.ContextWithImportConfigs(ctx, dang.ImportConfig{
		Name: "Dagger", Client: invocationClient{}, Schema: schema, AutoImport: true,
	})
}

func invokeDeclarationTest(ctx context.Context, env dang.ValueScope, name string) (string, error) {
	value, found, err := env.Lookup(ctx, "Demo")
	if err != nil || !found {
		return "", fmt.Errorf("constructor lookup: %t: %w", found, err)
	}
	object, err := value.(*dang.ConstructorFunction).Call(ctx, env, map[string]dang.Value{"name": dang.StringValue{Val: name}})
	if err != nil {
		return "", err
	}
	result, err := dang.EvalNode(ctx, env, &dang.FunCall{Fun: &dang.Select{
		Receiver: &dang.ValueNode{Val: object}, Field: &dang.Symbol{Name: "read"},
	}})
	if err != nil {
		return "", err
	}
	return result.(dang.StringValue).Val, nil
}

func TestReusableDeclarationsIsolatesConcurrentInvocations(t *testing.T) {
	dir := t.TempDir()
	source := `type Demo {
  name: String!
  read: String! { name + ":" + value }
}`
	if err := os.WriteFile(filepath.Join(dir, "main.dang"), []byte(source), 0600); err != nil {
		t.Fatal(err)
	}
	var preparations atomic.Int64
	run := func(ctx context.Context, dir string) (dang.ValueScope, error) {
		preparations.Add(1)
		return dang.RunDir(ctx, dir, false)
	}
	key := declarationKey{source: "one", schema: "string", directory: dir}
	var wg sync.WaitGroup
	for i := range 32 {
		name := fmt.Sprintf("caller-%d", i)
		ctx := declarationTestContext(t, name, "type Query { value: String! }")
		wg.Go(func() {
			env, err := loadDeclarationTest(ctx, key, run)
			if err != nil {
				t.Error(err)
				return
			}
			for j := range 3 {
				argument := fmt.Sprintf("argument-%d-%d", i, j)
				result, err := invokeDeclarationTest(ctx, env, argument)
				if err != nil || result != argument+":"+name {
					t.Errorf("request state leaked: result %q, error %v", result, err)
				}
			}
		})
	}
	wg.Wait()
	if preparations.Load() != 1 {
		t.Fatalf("prepared %d times", preparations.Load())
	}
	// Cached code has no fallback to the client that originally prepared it.
	env, err := loadDeclarationTest(t.Context(), key, run)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := invokeDeclarationTest(t.Context(), env, "missing"); err == nil || !strings.Contains(err.Error(), "no GraphQL client") {
		t.Fatalf("missing invocation client reused another caller: %v", err)
	}
}

func TestReusableDeclarationsRechecksSourceAndSchema(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "main.dang")
	source := `type Demo { name: String!; read: String! { name + ":" + value } }`
	if err := os.WriteFile(file, []byte(source), 0600); err != nil {
		t.Fatal(err)
	}
	run := func(ctx context.Context, dir string) (dang.ValueScope, error) { return dang.RunDir(ctx, dir, false) }
	ctx := declarationTestContext(t, "first", "type Query { value: String! }")
	key := declarationKey{source: "old", schema: "string", directory: dir}
	if _, err := loadDeclarationTest(ctx, key, run); err != nil {
		t.Fatal(err)
	}
	changed := strings.ReplaceAll(source, `name + ":"`, `name + "-edited:"`)
	if err := os.WriteFile(file, []byte(changed), 0600); err != nil {
		t.Fatal(err)
	}
	key.source = "edited"
	env, err := loadDeclarationTest(ctx, key, run)
	if err != nil {
		t.Fatal(err)
	}
	got, err := invokeDeclarationTest(ctx, env, "new")
	if err != nil || got != "new-edited:first" {
		t.Fatalf("source edit ignored: %q: %v", got, err)
	}
	key.schema = "integer"
	ctx = declarationTestContext(t, "second", "type Query { value: Int! }")
	if _, err := loadDeclarationTest(ctx, key, run); err == nil {
		t.Fatal("changed schema bypassed type checking")
	}
}

func TestReusableDeclarationsKeepsInitializationPerInvocation(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "main.dang"), []byte("let label: String! = value\ntype Demo { name: String!; read: String! { label } }"), 0600); err != nil {
		t.Fatal(err)
	}
	run := func(ctx context.Context, dir string) (dang.ValueScope, error) { return dang.RunDir(ctx, dir, false) }
	key := declarationKey{source: "side-effects", schema: "string", directory: dir}
	for _, name := range []string{"first", "second"} {
		ctx := declarationTestContext(t, name, "type Query { value: String! }")
		env, err := loadDeclarationTest(ctx, key, run)
		if err != nil {
			t.Fatal(err)
		}
		got, err := invokeDeclarationTest(ctx, env, "argument")
		if err != nil || got != name {
			t.Fatalf("initializer reused: %q: %v", got, err)
		}
	}
}

func TestReusableDeclarationsEligibility(t *testing.T) {
	cases := []struct {
		name, source string
		reusable     bool
	}{
		{"objects", "type Demo { name: String!; read: String! { name } }", true},
		{"top-level-value", "let label = \"init\"\ntype Demo { name: String! }", false},
		{"top-level-effect", "print(\"init\")\ntype Demo { name: String! }", false},
		{"statics", "type Demo { self { value: String! = \"init\" } }", false},
		{"nested-type", "type Demo { type Nested { name: String! } }", false},
		{"explicit-import", "import Dagger\ntype Demo { name: String! }", false},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			dir := t.TempDir()
			if err := os.WriteFile(filepath.Join(dir, "main.dang"), []byte(test.source), 0600); err != nil {
				t.Fatal(err)
			}
			got, err := dang.ReusableDirectoryDeclarations(t.Context(), dir)
			if err != nil || got != test.reusable {
				t.Fatalf("reusable %t: %v", got, err)
			}
		})
	}
	for _, source := range []string{"/tmp/dagger-go-ordered-discovery-inputs/go.dang", "/tmp/dagger-go-ordered-discovery-inputs/gomod/main.dang"} {
		t.Run(filepath.Base(filepath.Dir(source)), func(t *testing.T) {
			data, err := os.ReadFile(source)
			if os.IsNotExist(err) {
				t.Skip("local performance fixture unavailable")
			}
			if err != nil {
				t.Fatal(err)
			}
			dir := t.TempDir()
			if err := os.WriteFile(filepath.Join(dir, "main.dang"), data, 0600); err != nil {
				t.Fatal(err)
			}
			got, err := dang.ReusableDirectoryDeclarations(t.Context(), dir)
			if err != nil || !got {
				t.Fatalf("actual module source rejected: %t: %v", got, err)
			}
		})
	}
}

// Adapt the environment-only fixtures to the prepared declaration cache.
func loadDeclarationTest(ctx context.Context, key declarationKey, run dangSourceRunner) (dang.ValueScope, error) {
	prepared, err := reuseDangDeclarations(ctx, key, func(ctx context.Context, dir string) (*preparedDeclarations, error) {
		env, err := run(ctx, dir)
		return &preparedDeclarations{env: env}, err
	})
	if err != nil {
		return nil, err
	}
	return prepared.env, nil
}
