from pathlib import Path
import hashlib,json,subprocess,difflib
ROOT=Path('/home/dagger/dag');P=Path(__file__).resolve().parent;src=ROOT/'core/sdk/dang/v2/helpers.go';old=src.read_text();new=old
new=new.replace('''\t\t\tif registerTypes {
\t\t\t\t_, selfTypesOp''','''\t\t\tvar metadata *dangRegistrationMetadata
\t\t\tif registerTypes {
\t\t\t\t_, selfTypesOp''',1)
new=new.replace('''\t\t\t\tensureModuleSelfTypes(intro.Schema, modSource.Self(), modSrcDir)''','''\t\t\t\tmetadata = readDangRegistrationMetadata(modSrcDir, func(path string) (any, error) {
\t\t\t\t\treturn dang.ParseFile(path)
\t\t\t\t})
\t\t\t\tensureModuleSelfTypes(intro.Schema, modSource.Self(), metadata)''',1)
new=new.replace('retainDangObjectDirectives(directiveCtx, env, modSrcDir)','metadata.retainObjectDirectives(directiveCtx, env)',1)
start=new.index('// Dang validates object directives');end=new.index('// ensureModuleSelfTypes',start);new=new[:start]+new[end:]
new=new.replace('func ensureModuleSelfTypes(schema *introspection.Schema, src *core.ModuleSource, modSrcDir string)', 'func ensureModuleSelfTypes(schema *introspection.Schema, src *core.ModuleSource, metadata *dangRegistrationMetadata)',1)
new=new.replace('for _, localName := range moduleDeclaredTypeNames(modSrcDir, moduleName)', 'for _, localName := range metadata.declaredTypeNames(moduleName)',1)
start=new.index('// moduleDeclaredTypeNames parses');end=new.index('func runDangDirForModuleTypes',start);new=new[:start]+new[end:]
# os/filepath remain used elsewhere; strcase was used only in the removed helper.
if new.count('strcase.')==0:new=new.replace('\t"github.com/iancoleman/strcase"\n','')
if new.count('os.')==0:new=new.replace('\t"os"\n','')
start=new.index('\t\terr = modCtx.Self().Mount')
end=new.index('\n\t\tif err != nil {',start)
new=new[:start]+'''\t\terr = modCtx.Self().Mount(ctx, modCtx, func(path string) error {
\t\t\tmodSrcDir := filepath.Join(path, modSource.Self().SourceSubpath)
\t\t\tenv, err = runDangSourceWithRegistration(ctx, modSrcDir, registerTypes, intro.Schema, modSource.Self(), runSource, stdio.Stderr)
\t\t\treturn err
\t\t})'''+new[end:]
(P/'source/helpers.go').write_text(new);(P/'helpers.baseline.go.txt').write_text(old)
assert new!=old and new.count('runDangSourceWithRegistration')==1
