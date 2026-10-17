package dangv2

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/vito/dang/v2/pkg/dang"
)

func preparedSchemaContext(ctx context.Context, prepared *preparedDeclarations) context.Context {
	return dang.ContextWithImportConfigs(ctx, dang.ImportConfig{
		Name: "Dagger", Client: invocationClient{}, Schema: prepared.schema, AutoImport: true,
	})
}

func prepareSchemaFixture(ctx context.Context, dir, sdl string) (*preparedDeclarations, error) {
	schema, err := dang.SchemaFromSDL(sdl, "schema.graphqls")
	if err != nil {
		return nil, err
	}
	prepared := &preparedDeclarations{schema: schema}
	env, err := dang.RunDir(preparedSchemaContext(ctx, prepared), dir, false)
	if err != nil {
		return nil, err
	}
	prepared.env = env
	return prepared, nil
}

func TestPreparedSchemaRetainsCurrentClientUnderConcurrency(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "main.dang"), []byte(`type Demo {
  name: String!
  read: String! { name + ":" + value }
}`), 0600); err != nil {
		t.Fatal(err)
	}
	key := declarationKey{source: "prepared-clients", schema: "string", directory: dir}
	var reads atomic.Int64
	prepare := func(ctx context.Context, dir string) (*preparedDeclarations, error) {
		reads.Add(1)
		return prepareSchemaFixture(ctx, dir, "type Query { value: String! }")
	}
	var wg sync.WaitGroup
	for i := range 16 {
		wg.Go(func() {
			name := fmt.Sprintf("client-%d", i)
			ctx := context.WithValue(t.Context(), invocationClientKey{}, declarationTestClient(name))
			ctx = dang.ContextWithImportConfigs(ctx)
			prepared, err := reuseDangDeclarations(ctx, key, prepare)
			if err != nil {
				t.Error(err)
				return
			}
			for j := range 3 {
				argument := fmt.Sprintf("argument-%d-%d", i, j)
				got, err := invokeDeclarationTest(preparedSchemaContext(ctx, prepared), prepared.env, argument)
				if err != nil || got != argument+":"+name {
					t.Errorf("shared schema retained another invocation: %q: %v", got, err)
				}
			}
		})
	}
	wg.Wait()
	if reads.Load() != 1 {
		t.Fatalf("read schema %d times, want one preparation", reads.Load())
	}
}

func TestPreparedSchemaRetriesAndInvalidates(t *testing.T) {
	dir := t.TempDir()
	sourceFile := filepath.Join(dir, "main.dang")
	source := `type Demo { name: String!; read: String! { name + ":" + value } }`
	if err := os.WriteFile(sourceFile, []byte(source), 0600); err != nil {
		t.Fatal(err)
	}
	ctx := context.WithValue(t.Context(), invocationClientKey{}, declarationTestClient("current"))
	ctx = dang.ContextWithImportConfigs(ctx)
	key := declarationKey{source: "old", schema: "string", directory: dir}
	reads := 0
	sdl := "type Query { value: String! }"
	prepare := func(ctx context.Context, dir string) (*preparedDeclarations, error) {
		reads++
		if reads == 1 {
			return nil, io.ErrUnexpectedEOF
		}
		return prepareSchemaFixture(ctx, dir, sdl)
	}
	if _, err := reuseDangDeclarations(ctx, key, prepare); !errors.Is(err, io.ErrUnexpectedEOF) {
		t.Fatalf("lost schema read error: %v", err)
	}
	first, err := reuseDangDeclarations(ctx, key, prepare)
	if err != nil {
		t.Fatal(err)
	}
	again, err := reuseDangDeclarations(ctx, key, prepare)
	if err != nil || first != again || reads != 2 {
		t.Fatalf("prepared schema not reused: reads=%d, error=%v", reads, err)
	}
	key.schema = "integer"
	// A new SDK invocation has a fresh import/type-identity cache.
	ctx = dang.ContextWithImportConfigs(context.WithValue(t.Context(), invocationClientKey{}, declarationTestClient("current")))
	sdl = "type Query { value: Int! }"
	if _, err := reuseDangDeclarations(ctx, key, prepare); err == nil {
		t.Fatal("changed schema bypassed type checking")
	}
	key.schema = "string"
	key.source = "edited"
	ctx = dang.ContextWithImportConfigs(context.WithValue(t.Context(), invocationClientKey{}, declarationTestClient("current")))
	sdl = "type Query { value: String! }"
	if err := os.WriteFile(sourceFile, []byte(`type Demo { name: String!; read: String! { name + "-edited:" + value } }`), 0600); err != nil {
		t.Fatal(err)
	}
	edited, err := reuseDangDeclarations(ctx, key, prepare)
	if err != nil {
		t.Fatal(err)
	}
	got, err := invokeDeclarationTest(preparedSchemaContext(ctx, edited), edited.env, "argument")
	if err != nil || got != "argument-edited:current" || reads != 4 {
		t.Fatalf("changed source reused prepared code: %q, reads=%d: %v", got, reads, err)
	}
}

func TestPreparedSchemaKeepsInitializersPerInvocation(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "main.dang"), []byte(`let label: String! = value
type Demo { name: String!; read: String! { label } }`), 0600); err != nil {
		t.Fatal(err)
	}
	key := declarationKey{source: "initializers", schema: "string", directory: dir}
	reads := 0
	prepare := func(ctx context.Context, dir string) (*preparedDeclarations, error) {
		reads++
		return prepareSchemaFixture(ctx, dir, "type Query { value: String! }")
	}
	for _, name := range []string{"first", "second"} {
		ctx := context.WithValue(t.Context(), invocationClientKey{}, declarationTestClient(name))
		ctx = dang.ContextWithImportConfigs(ctx)
		prepared, err := reuseDangDeclarations(ctx, key, prepare)
		if err != nil {
			t.Fatal(err)
		}
		got, err := invokeDeclarationTest(preparedSchemaContext(ctx, prepared), prepared.env, "argument")
		if err != nil || got != name {
			t.Fatalf("reused an invocation's initialization: %q: %v", got, err)
		}
	}
	if reads != 2 {
		t.Fatalf("read schema %d times, want per-invocation preparation", reads)
	}
}
