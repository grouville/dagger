package dangv2

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/dagger/dagger/core"
	"github.com/stretchr/testify/require"
	"github.com/vito/dang/v2/pkg/dang"
	"github.com/vito/dang/v2/pkg/introspection"
)

func metadataSource(t *testing.T, dir, name, source string) {
	t.Helper()
	require.NoError(t, os.WriteFile(filepath.Join(dir, name), []byte(source), 0600))
}

func metadataConstructor(name string) *dang.ConstructorFunction {
	return &dang.ConstructorFunction{ObjectName: name, ObjectType: dang.NewType(name, dang.ObjectKind)}
}

func TestDangRegistrationMetadataParsesOnceForBothConsumers(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	metadataSource(t, dir, "z.dang", "type Zed @collection {}")
	metadataSource(t, dir, "a.dang", "type Alpha @collection {}")
	metadataSource(t, dir, "ignored.txt", "not Dang")
	require.NoError(t, os.Mkdir(filepath.Join(dir, "sub.dang"), 0700))
	var parsed []string
	metadata := readDangRegistrationMetadata(dir, func(path string) (any, error) {
		parsed = append(parsed, filepath.Base(path))
		return dang.ParseFile(path)
	})
	require.Equal(t, []string{"a.dang", "z.dang"}, parsed)
	require.Equal(t, []string{"Example", "Alpha", "Zed"}, metadata.declaredTypeNames("example"))
	schema := &introspection.Schema{}
	ensureModuleSelfTypes(schema, &core.ModuleSource{ModuleName: "example", ModuleOriginalName: "example"}, metadata)
	env := dang.NewObject(nil)
	for _, name := range []string{"Alpha", "Zed"} {
		env.Bind(name, metadataConstructor(name), dang.PublicVisibility)
	}
	require.NoError(t, metadata.retainObjectDirectives(t.Context(), env))
	require.Equal(t, []string{"a.dang", "z.dang"}, parsed, "consuming names and directives must not parse again")
	for _, name := range []string{"Alpha", "Zed"} {
		value, found, err := env.Lookup(t.Context(), name)
		require.NoError(t, err)
		require.True(t, found)
		got := value.(*dang.ConstructorFunction).ObjectType.GetDirectives("")
		require.Len(t, got, 1)
		require.Equal(t, "collection", got[0].Name)
		require.Nil(t, got[0].GetInferredType())
	}
}

func TestDangRegistrationMetadataNamesAndPrivateDirectives(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	metadataSource(t, dir, "main.dang", "")
	directive := &dang.DirectiveApplication{Name: "marker"}
	file := &dang.FileBlock{Forms: []dang.Node{
		&dang.ObjectDecl{Name: &dang.Symbol{Name: "Main"}, Visibility: dang.PublicVisibility},
		&dang.ObjectDecl{Name: &dang.Symbol{Name: "Hidden"}, Visibility: dang.PrivateVisibility, Directives: []*dang.DirectiveApplication{directive}},
		&dang.InterfaceDecl{Name: &dang.Symbol{Name: "Face"}, Visibility: dang.PublicVisibility},
		&dang.EnumDecl{Name: &dang.Symbol{Name: "Mode"}, Visibility: dang.PublicVisibility},
		&dang.ScalarDecl{Name: &dang.Symbol{Name: "Token"}, Visibility: dang.PublicVisibility},
		&dang.ObjectDecl{Name: &dang.Symbol{Name: "Face"}, Visibility: dang.PublicVisibility},
	}}
	metadata := readDangRegistrationMetadata(dir, func(string) (any, error) { return file, nil })
	require.Equal(t, []string{"Main", "Face", "Mode", "Token"}, metadata.declaredTypeNames("main"))
	existing := &introspection.Type{Name: core.NamespaceObject("Face", "alias", "main"), Kind: introspection.TypeKindInterface}
	schema := &introspection.Schema{Types: introspection.Types{existing}}
	ensureModuleSelfTypes(schema, &core.ModuleSource{ModuleName: "alias", ModuleOriginalName: "main"}, metadata)
	require.Same(t, existing, schema.Types.Get(existing.Name), "do not replace an existing real type with a placeholder")
	require.Nil(t, schema.Types.Get(core.NamespaceObject("Hidden", "alias", "main")))
	hidden := metadataConstructor("Hidden")
	env := dang.NewObject(nil)
	env.Bind("Hidden", hidden, dang.PrivateVisibility)
	require.Empty(t, hidden.ObjectType.GetDirectives(""))
	require.NoError(t, metadata.retainObjectDirectives(t.Context(), env))
	require.Same(t, directive, hidden.ObjectType.GetDirectives("")[0])
	require.Nil(t, directive.GetInferredType(), "collection must not infer directive AST")
}

type metadataErrorScope struct {
	dang.ValueScope
	name string
	err  error
}

func (s metadataErrorScope) Lookup(ctx context.Context, name string) (dang.Value, bool, error) {
	if name == s.name {
		return nil, false, s.err
	}
	return s.ValueScope.Lookup(ctx, name)
}

func TestDangRegistrationMetadataDeferredErrorOrder(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	metadataSource(t, dir, "a.dang", "type Alpha @collection {}")
	metadataSource(t, dir, "b.dang", "broken")
	metadataSource(t, dir, "c.dang", "type Later {}")
	parseErr := errors.New("second file parser error")
	metadata := readDangRegistrationMetadata(dir, func(path string) (any, error) {
		if filepath.Base(path) == "b.dang" {
			return nil, parseErr
		}
		return dang.ParseFile(path)
	})
	require.Equal(t, []string{"Main", "Alpha", "Later"}, metadata.declaredTypeNames("main"), "name discovery continues after a malformed file")
	lookupErr := errors.New("first file lookup error")
	require.ErrorIs(t, metadata.retainObjectDirectives(t.Context(), metadataErrorScope{ValueScope: dang.NewObject(nil), name: "Alpha", err: lookupErr}), lookupErr)
	require.ErrorIs(t, metadata.retainObjectDirectives(t.Context(), dang.NewObject(nil)), parseErr)
	missing := readDangRegistrationMetadata(filepath.Join(dir, "missing"), func(string) (any, error) { t.Fatal("must not parse absent directory"); return nil, nil })
	require.Equal(t, []string{"Main"}, missing.declaredTypeNames("main"))
	require.ErrorIs(t, missing.retainObjectDirectives(t.Context(), dang.NewObject(nil)), os.ErrNotExist)
}

func TestDangRegistrationMetadataRunnerErrorAndRuntimeSkip(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	metadataSource(t, dir, "bad.dang", "type {")
	original := inferReport(errors.New("runner diagnostic wins"))
	var output bytes.Buffer
	_, err := runDangSourceWithRegistration(t.Context(), dir, true, &introspection.Schema{}, &core.ModuleSource{ModuleName: "main"}, func(context.Context, string) (dang.ValueScope, error) { return nil, original }, &output)
	require.ErrorIs(t, err, original)
	require.Equal(t, strings.TrimRight(original.Error(), "\n")+"\n", output.String())
	require.EqualError(t, err, "runner diagnostic wins")
	output.Reset()
	env := dang.NewObject(nil)
	got, err := runDangSourceWithRegistration(t.Context(), filepath.Join(dir, "does-not-exist"), false, nil, nil, func(context.Context, string) (dang.ValueScope, error) { return env, nil }, &output)
	require.NoError(t, err)
	require.Same(t, env, got)
	require.Empty(t, output.String(), "ordinary runtime must not inspect metadata files")
	_, err = runDangSourceWithRegistration(t.Context(), dir, true, nil, nil, func(context.Context, string) (dang.ValueScope, error) { return env, nil }, &output)
	require.Error(t, err)
	require.Empty(t, output.String(), "deferred metadata errors do not acquire the runner's rendering path")
}

func TestDangRegistrationMetadataOwnedSnapshotsAndDirectiveScope(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	metadataSource(t, dir, "main.dang", "type Example @marker(value: label) {}")
	parse := func(path string) (any, error) { return dang.ParseFile(path) }
	first := readDangRegistrationMetadata(dir, parse)
	second := readDangRegistrationMetadata(dir, parse)
	require.NoError(t, first.files[0].err)
	require.NoError(t, second.files[0].err)
	a := first.files[0].objects[0].directives[0]
	b := second.files[0].objects[0].directives[0]
	require.NotSame(t, a, b)
	require.NotSame(t, a.Args[0].Value, b.Args[0].Value)
	env := dang.NewObject(dang.NewType("FixtureScope", dang.ObjectKind))
	env.Bind("label", dang.StringValue{Val: "file-local"}, dang.PrivateVisibility)
	ctor := metadataConstructor("Example")
	ctor.Closure = env
	env.Bind("Example", ctor, dang.PublicVisibility)
	require.NoError(t, first.retainObjectDirectives(t.Context(), env))
	value, err := evalDirectiveArg(t.Context(), ctor.Closure, ctor.ObjectType.GetDirectives("")[0].Args[0].Value)
	require.NoError(t, err)
	require.Equal(t, "file-local", value)
	a.Name = "changed"
	require.Equal(t, "marker", b.Name)
	var wg sync.WaitGroup
	for range 8 {
		wg.Go(func() {
			m := readDangRegistrationMetadata(dir, parse)
			if m.files[0].err != nil {
				t.Error(m.files[0].err)
				return
			}
			m.files[0].objects[0].directives[0].Name = "local"
		})
	}
	wg.Wait()
	require.Equal(t, "marker", b.Name)
	metadataSource(t, dir, "main.dang", "type Edited {}")
	require.Equal(t, []string{"Example", "Edited"}, readDangRegistrationMetadata(dir, parse).declaredTypeNames("example"))
	require.Equal(t, []string{"Example"}, second.declaredTypeNames("example"), "an earlier immutable snapshot owns its own metadata")
}

func TestDangRegistrationMetadataRealDeclaration(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	metadataSource(t, dir, "main.dang", `type Main {
  selfType: Dagger.Main! { self }
  items: Items! { Items(names: ["a"]) }
}
type Items @collection { pub names: [String!]! }
`)
	schema := &introspection.Schema{
		Types:      introspection.Types{&introspection.Type{Name: "Query", Kind: introspection.TypeKindObject}},
		Directives: []*introspection.DirectiveDef{{Name: "collection", Locations: []string{"OBJECT"}}},
	}
	schema.QueryType.Name = "Query"
	source := &core.ModuleSource{ModuleName: "main", ModuleOriginalName: "main"}
	metadata := readDangRegistrationMetadata(dir, func(path string) (any, error) { return dang.ParseFile(path) })
	ensureModuleSelfTypes(schema, source, metadata)
	require.NotNil(t, schema.Types.Get("Main"), "self-type placeholder must exist before declaration")
	ctx := dang.ContextWithImportConfigs(t.Context(), dang.ImportConfig{Name: "Dagger", Schema: schema, AutoImport: true})
	env, err := runDangDirForModuleTypes(ctx, dir)
	require.NoError(t, err, "real DeclareDir must resolve Dagger.Main and infer object directive")
	for _, name := range []string{"Main", "Items"} {
		value, found, err := env.Lookup(ctx, name)
		require.NoError(t, err)
		require.True(t, found)
		constructor, ok := value.(*dang.ConstructorFunction)
		require.True(t, ok)
		require.NotNil(t, constructor.ObjectType)
	}
	items, _, err := env.Lookup(ctx, "Items")
	require.NoError(t, err)
	constructor := items.(*dang.ConstructorFunction)
	require.Empty(t, constructor.ObjectType.GetDirectives(""), "production Dang v2.1.4 does not retain object directives itself")
	raw := metadata.files[0].objects[0].directives[0]
	require.Nil(t, raw.GetInferredType(), "DeclareDir must not infer the independent metadata AST")
	require.NoError(t, metadata.retainObjectDirectives(ctx, env))
	require.Same(t, raw, constructor.ObjectType.GetDirectives("")[0])
	require.Equal(t, "collection", raw.Name)
	require.Nil(t, raw.GetInferredType(), "attaching a directive must not infer it again")
}
