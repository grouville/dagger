package pythongenerator

import (
	"bytes"
	"context"
	"fmt"
	"path/filepath"
	"sort"

	"github.com/psanford/memfs"

	"github.com/dagger/dagger/cmd/codegen/generator"
	"github.com/dagger/dagger/cmd/codegen/generator/python/templates"
	"github.com/dagger/dagger/cmd/codegen/introspection"
)

const (
	ClientGenFile   = "gen.py"
	clientTargetDir = "src/dagger/client"
)

type PythonGenerator struct {
	Config generator.Config
}

func (g *PythonGenerator) GenerateModule(_ context.Context, schema *introspection.Schema, schemaVersion string) (*generator.GeneratedState, error) {
	target := filepath.Join(g.Config.ModuleConfig.ModuleSourcePath, "sdk", clientTargetDir, ClientGenFile)
	return generate(g.Config, target, schema, schemaVersion)
}

func (g *PythonGenerator) GenerateClient(_ context.Context, schema *introspection.Schema, schemaVersion string) (*generator.GeneratedState, error) {
	target := filepath.Join(clientTargetDir, ClientGenFile)
	return generate(g.Config, target, schema, schemaVersion)
}

func (g *PythonGenerator) GenerateLibrary(_ context.Context, schema *introspection.Schema, schemaVersion string) (*generator.GeneratedState, error) {
	target := filepath.Join(clientTargetDir, ClientGenFile)
	return generate(g.Config, target, schema, schemaVersion)
}

func (g *PythonGenerator) GenerateTypeDefs(_ context.Context, _ *introspection.Schema, _ string) (*generator.GeneratedState, error) {
	return nil, fmt.Errorf("not implemented for %s SDK", generator.SDKLangPython)
}

func generate(config generator.Config, target string, schema *introspection.Schema, schemaVersion string) (*generator.GeneratedState, error) {
	generator.SetSchema(schema)
	generator.SetSchemaParents(schema)

	// Keep deterministic ordering similar to the TS generator
	sort.SliceStable(schema.Types, func(i, j int) bool {
		return schema.Types[i].Name < schema.Types[j].Name
	})
	for _, t := range schema.Types {
		sort.SliceStable(t.Fields, func(i, j int) bool {
			in, jn := t.Fields[i].Name, t.Fields[j].Name
			switch {
			case in == "id" && jn == "id":
				return false
			case in == "id":
				return true
			case jn == "id":
				return false
			default:
				return in < jn
			}
		})
	}

	tmpl := templates.New(schemaVersion, config)
	data := struct {
		Schema        *introspection.Schema
		SchemaVersion string
		Types         []*introspection.Type
	}{
		Schema:        schema,
		SchemaVersion: schemaVersion,
		Types:         schema.Types,
	}

	var b bytes.Buffer
	if err := tmpl.ExecuteTemplate(&b, "api", data); err != nil {
		return nil, err
	}

	mfs := memfs.New()
	if err := mfs.MkdirAll(filepath.Dir(target), 0o700); err != nil {
		return nil, fmt.Errorf("failed to create target directory %s: %w", filepath.Dir(target), err)
	}
	if err := mfs.WriteFile(target, b.Bytes(), 0o600); err != nil {
		return nil, fmt.Errorf("failed to write client file at %s: %w", target, err)
	}

	return &generator.GeneratedState{
		Overlay: mfs,
	}, nil
}
