from pathlib import Path
import json
ROOT=Path('/home/dagger/dag'); OUT=Path('/tmp/collections-perf/sdk-edit-audit/ts-generic')
# Isolated engine overlay. Keep the measured fixture prototype untouched.
prior=Path('/tmp/collections-perf/sdk-edit-audit/ts-static')
helper=(prior/'helper.go.fragment').read_text().replace(' || src.Self().ModuleOriginalName != "frontend"','').replace('ts-static-frontend-v1','ts-static-metadata-v1').replace('static TS metadata fixture','static TS metadata version')
helper=helper.replace('// prototypeStaticTypeScriptTypes is an intentionally fixture-gated experiment.', '// prototypeStaticTypeScriptTypes is a generic, opt-in static metadata experiment.')
helper=helper.replace('Version string `json:"version"`','Version string `json:"version"`\n\t\tModuleName string `json:"moduleName"`')
needle='\tseen := make(map[string]bool, len(manifest.Inputs))'
helper=helper.replace(needle, '''\tif manifest.ModuleName != src.Self().ModuleOriginalName {
\t\treturn nil, false, fmt.Errorf("static TS metadata module identity mismatch: got %q, expected %q", manifest.ModuleName, src.Self().ModuleOriginalName)
\t}
''' + needle)
helper=helper.replace('path != metadataDir+"/main.dang"', 'path != metadataDir+"/main.dang" && path != metadataDir+"/module.json"')
helper=helper.replace('\t\tdata, err := readFile(path)\n\t\tif err != nil {\n\t\t\treturn nil, false, err\n\t\t}\n\t\tif fmt.Sprintf("%x", sha256.Sum256(data)) != expected {', '\t\tvar digest dagql.String\n\t\tif err := dag.Select(ctx, dir, &digest,\n\t\t\tdagql.Selector{Field: "file", Args: []dagql.NamedInput{{Name: "path", Value: dagql.String(path)}}},\n\t\t\tdagql.Selector{Field: "digest", Args: []dagql.NamedInput{{Name: "excludeMetadata", Value: dagql.Boolean(true)}}},\n\t\t); err != nil { return nil, false, err }\n\t\tif string(digest) != expected {')
(OUT/'helper.go.fragment').write_text(helper)
source=(prior/'modulesource.go').read_text();start=source.index('// prototypeStaticTypeScriptTypes is an intentionally fixture-gated experiment.')
(OUT/'modulesource.go').write_text(source[:start]+helper)
overlay=json.loads((prior/'engine-overlay.json').read_text());overlay['Replace'][str(ROOT/'core/schema/modulesource.go')]=str(OUT/'modulesource.go');(OUT/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
# Main generator emits both files atomically from one analyzer model.
p=ROOT/'cmd/codegen/generator/typescript/entrypoint.go';src=p.read_text();needle='\treturn &generator.GeneratedState{Overlay: mfs}, nil'
assert src.count(needle)==1
src=src.replace(needle,'''\tmetadata, err := templates.RenderDangTypesEntrypoint(&module)
\tif err != nil {
\t\treturn nil, fmt.Errorf("render static metadata: %w", err)
\t}
\tif err := mfs.MkdirAll(".dagger-static-types", 0o755); err != nil { return nil, err }
\tif err := mfs.WriteFile(".dagger-static-types/main.dang", []byte(metadata), 0o644); err != nil { return nil, err }
\tinfo, err := json.Marshal(struct {
\t\tName string `json:"name"`
\t\tDescription string `json:"description"`
\t}{module.Name, module.Description})
\tif err != nil { return nil, err }
\tif err := mfs.WriteFile(".dagger-static-types/module.json", info, 0o644); err != nil { return nil, err }
''' + needle)
(OUT/'entrypoint.go').write_text(src)
# Preserve EmitEntrypoint's File API for execution paths. Generation uses directory.
p=ROOT/'sdk/typescript/runtime/introspector.go';src=p.read_text();old='''\t// Step 2: hand the typedef JSON to `cmd/codegen generate-entrypoint`.''';assert old in src
start=src.index('func (i *Introspector) EmitEntrypoint(');brace=src.index(') *dagger.File {',start)
wrapper='''func (i *Introspector) EmitEntrypoint(
 moduleName string, sourceCode *dagger.Directory, clientBindings *dagger.Directory, sdkSourceDir *dagger.Directory,
) *dagger.File {
 return i.emitEntrypointArtifacts(moduleName, sourceCode, clientBindings, sdkSourceDir).File(EntrypointExecutableFile)
}

'''
src=src[:start]+wrapper+src[start:].replace('func (i *Introspector) EmitEntrypoint(', 'func (i *Introspector) emitEntrypointArtifacts(',1).replace(') *dagger.File {', ') *dagger.Directory {',1)
src=src.replace('File("/work/" + entrypointFile)', 'Directory("/work").\n\t\tFilter([]string{entrypointFile, ".dagger-static-types/**"})')
# Avoid assuming generated Directory.Filter exists; WithDirectory(include:) is established API.
src=src.replace('return dag.Container().\n\t\tFrom', 'output := dag.Container().\n\t\tFrom',1)
src=src.replace('Directory("/work").\n\t\tFilter([]string{entrypointFile, ".dagger-static-types/**"})','Directory("/work")\n\treturn dag.Directory().WithDirectory(".", output, dagger.DirectoryWithDirectoryOpts{Include: []string{entrypointFile, ".dagger-static-types/**"}})')
(OUT/'introspector.go').write_text(src)
p=ROOT/'sdk/typescript/runtime/main.go';src=p.read_text();src=src.replace('entrypoint := NewIntrospector(t.SDKSourceDir).EmitEntrypoint(', 'entrypoint := NewIntrospector(t.SDKSourceDir).emitEntrypointArtifacts(',1)
src=src.replace('codegen = codegen.WithFile(EntrypointExecutableFile, entrypoint)', '''codegen = codegen.WithDirectory(".", entrypoint)
\tcodegen, err = sealStaticMetadata(ctx, codegen)
\tif err != nil { return nil, fmt.Errorf("seal static metadata: %w", err) }''',1)
src=src.replace('GenDir + "/**",','GenDir + "/**",\n\t\t\t".dagger-static-types/**",',1)
(OUT/'runtime_main.go').write_text(src)
replacements={
 str(ROOT/'cmd/codegen/generator/typescript/templates/entrypoint_dang.go'):str(OUT/'entrypoint_dang.go'),
 str(ROOT/'cmd/codegen/generator/typescript/entrypoint.go'):str(OUT/'entrypoint.go'),
 str(ROOT/'sdk/typescript/runtime/introspector.go'):str(OUT/'introspector.go'),
 str(ROOT/'sdk/typescript/runtime/main.go'):str(OUT/'runtime_main.go'),
 str(ROOT/'sdk/typescript/runtime/static_metadata.go'):str(OUT/'static_metadata.go'),
}
(OUT/'sdk-overlay.json').write_text(json.dumps({'Replace':replacements},indent=2)+'\n')
