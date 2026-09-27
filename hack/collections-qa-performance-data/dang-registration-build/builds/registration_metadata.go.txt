package dangv2

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/engine/wcprof"
	"github.com/iancoleman/strcase"
	"github.com/vito/dang/v2/pkg/dang"
	"github.com/vito/dang/v2/pkg/introspection"
)

// dangRegistrationMetadata owns parser-only metadata for one registration on an
// immutable mounted module Directory. Its nodes are never passed to the source
// runner, inferred, cached, or reused by another registration.
type dangRegistrationMetadata struct {
	dir     string
	readErr error
	files   []dangRegistrationFile
}

type dangRegistrationFile struct {
	path    string
	err     error
	names   []string
	objects []dangRegistrationObject
}

type dangRegistrationObject struct {
	name       string
	directives []*dang.DirectiveApplication
}

// Both metadata consumers see the same sorted files. Parsing failures are kept
// in file order rather than returned now: name discovery is best-effort, and the
// source runner retains precedence for rendered parse/inference diagnostics.
func readDangRegistrationMetadata(dir string, parse func(string) (any, error)) *dangRegistrationMetadata {
	metadata := &dangRegistrationMetadata{dir: dir}
	entries, err := os.ReadDir(dir)
	if err != nil {
		metadata.readErr = err
		return metadata
	}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".dang" {
			continue
		}
		file := dangRegistrationFile{path: filepath.Join(dir, entry.Name())}
		root, err := parse(file.path)
		if err != nil {
			file.err = err
			metadata.files = append(metadata.files, file)
			continue
		}
		block, ok := root.(*dang.FileBlock)
		if !ok {
			metadata.files = append(metadata.files, file)
			continue
		}
		for _, form := range block.Forms {
			switch decl := form.(type) {
			case *dang.ObjectDecl:
				if decl.Visibility >= dang.PublicVisibility && decl.Name != nil {
					file.names = append(file.names, decl.Name.Name)
				}
				if len(decl.Directives) > 0 {
					file.objects = append(file.objects, dangRegistrationObject{name: decl.Name.Name, directives: decl.Directives})
				}
			case *dang.InterfaceDecl:
				if decl.Visibility >= dang.PublicVisibility && decl.Name != nil {
					file.names = append(file.names, decl.Name.Name)
				}
			case *dang.EnumDecl:
				if decl.Visibility >= dang.PublicVisibility && decl.Name != nil {
					file.names = append(file.names, decl.Name.Name)
				}
			case *dang.ScalarDecl:
				if decl.Visibility >= dang.PublicVisibility && decl.Name != nil {
					file.names = append(file.names, decl.Name.Name)
				}
			}
		}
		metadata.files = append(metadata.files, file)
	}
	return metadata
}

func (metadata *dangRegistrationMetadata) declaredTypeNames(moduleName string) []string {
	seen := map[string]struct{}{}
	var names []string
	add := func(name string) {
		if name == "" {
			return
		}
		if _, ok := seen[name]; ok {
			return
		}
		seen[name] = struct{}{}
		names = append(names, name)
	}
	// Keep the main-type fallback even when directory reading or parsing fails.
	add(strcase.ToCamel(moduleName))
	if metadata.readErr != nil {
		slog.Debug("ensureModuleSelfTypes: read module dir", "dir", metadata.dir, "error", metadata.readErr)
		return names
	}
	for _, file := range metadata.files {
		if file.err != nil {
			slog.Debug("ensureModuleSelfTypes: parse module file", "file", filepath.Base(file.path), "error", file.err)
			continue
		}
		for _, name := range file.names {
			add(name)
		}
	}
	return names
}

// Apply only after runSource succeeds. File-local lookup errors still precede
// parse errors from later files, exactly as the former parse-and-apply loop did.
func (metadata *dangRegistrationMetadata) retainObjectDirectives(ctx context.Context, env dang.ValueScope) error {
	if metadata.readErr != nil {
		return metadata.readErr
	}
	for _, file := range metadata.files {
		if file.err != nil {
			return file.err
		}
		for _, object := range file.objects {
			value, found, err := env.Lookup(ctx, object.name)
			if err != nil {
				return err
			}
			if constructor, ok := value.(*dang.ConstructorFunction); found && ok {
				constructor.ObjectType.SetDirectives("", object.directives)
			}
		}
	}
	return nil
}

// Keep source diagnostics ahead of the deferred directive metadata errors. This
// function operates only on an already mounted immutable module Directory.
func runDangSourceWithRegistration(ctx context.Context, dir string, registerTypes bool, schema *introspection.Schema, source *core.ModuleSource, runSource dangSourceRunner, stderr io.Writer) (dang.ValueScope, error) {
	var metadata *dangRegistrationMetadata
	if registerTypes {
		_, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "dang.selfTypes", wcprof.OpOpts{})
		metadata = readDangRegistrationMetadata(dir, func(path string) (any, error) { return dang.ParseFile(path) })
		ensureModuleSelfTypes(schema, source, metadata)
		op.End(wcprof.OutcomeOK)
	}
	sourceCtx, sourceOp := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "dang.runSource", wcprof.OpOpts{})
	env, err := runSource(sourceCtx, dir)
	sourceOp.EndErr(err)
	if err != nil {
		if isDangSourceError(err) {
			return nil, reportDangSourceError(stderr, err)
		}
		return nil, fmt.Errorf("run dir: %w", err)
	}
	if registerTypes {
		directiveCtx, op := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "dang.objectDirectives", wcprof.OpOpts{})
		err = metadata.retainObjectDirectives(directiveCtx, env)
		op.EndErr(err)
		if err != nil {
			return env, err
		}
	}
	return env, nil
}
