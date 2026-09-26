from pathlib import Path
import hashlib,json,shutil
root=Path('/home/dagger/dag')
out=Path('/tmp/collections-perf/sdk-edit-audit/ts-static')
base=Path('/tmp/collections-perf/normal-baseline/greetings-split')
app=out/'greetings'
if not app.exists():
    shutil.copytree(base,app,symlinks=True)
mod=app/'.dagger/modules/frontend'
meta=mod/'.dagger-static-types'
meta.mkdir(exist_ok=True)
# Pinned fixture. The production emitter should use templates.TypedefModule,
# which already emits precisely these declarations in __dagger.entrypoint.ts.
(meta/'main.dang').write_text('''# Diagnostic fixture: literal TypeDefs from the generated TS register().
# Calls still use the original TS runtime; this entrypoint is types-only.
type Entrypoint implements ModuleEntrypoint {
  pub types(workspace: Workspace!): [TypeDef!]! {
    let obj = typeDef.withObject("Frontend", sourceMap: sourceMap("src/index.ts", 15, 14))
      .withFunction(function("build", typeDef.withObject("Directory"))
        .withSourceMap(sourceMap("src/index.ts", 24, 3)))
      .withFunction(function("serve", typeDef.withObject("Service"))
        .withSourceMap(sourceMap("src/index.ts", 30, 3)).withUp)
      .withField("source", typeDef.withObject("Directory"), sourceMap: sourceMap("src/index.ts", 17, 3))
    [obj.withConstructor(function("", obj)
      .withArg("source", typeDef.withObject("Directory"), defaultPath: "/website", sourceMap: sourceMap("src/index.ts", 19, 54)))]
  }
  pub call(workspace: Workspace!, receiverType: String!, receiverValue: JSON, fnName: String!, fnArgs: JSON!): JSON! {
    raise "types-only prototype must delegate calls to the original TypeScript runtime"
  }
}
''')
inputs={}
# Pin original fixture inputs once; rerunning preparation must never bless an
# edited API against unchanged hand-emitted metadata.
pinned=out/'pinned-inputs.json'
fixture=base/'.dagger/modules/frontend'
for p in sorted(fixture.rglob('*')):
    rel=p.relative_to(fixture).as_posix()
    if rel.startswith(('.dagger-static-types/', 'node_modules/', '.git/')) or p.is_dir(): continue
    if p.is_symlink(): raise SystemExit('Prototype does not support symlink metadata inputs: '+rel)
    inputs[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
if pinned.exists():
    inputs=json.loads(pinned.read_text())
else:
    pinned.write_text(json.dumps(inputs,indent=2)+'\n')
manifest={'version':'ts-static-frontend-v1','description':'A generated module for Frontend functions','inputs':inputs,'entrypointSHA256':hashlib.sha256((meta/'main.dang').read_bytes()).hexdigest()}
(meta/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Source copy composes with the existing complete SDK stack, not shared source.
overlay=json.loads(Path('/tmp/collections-perf/sdk-edit-audit/engine-combined-overlay.json').read_text())
source=Path(overlay['Replace'][str(root/'core/schema/modulesource.go')]).read_text()
source=source.replace('"context"','"context"\n\t"crypto/sha256"',1)
source=source.replace('"github.com/dagger/dagger/engine"', '"github.com/dagger/dagger/engine"\n\t"github.com/dagger/dagger/engine/wcprof"', 1)
source=source.replace('"github.com/dagger/dagger/core/sdk"','"github.com/dagger/dagger/core/sdk"\n\tdangv2 "github.com/dagger/dagger/core/sdk/dang/v2"',1)
needle='\ttypeDefsImpl, typeDefsEnabled := src.Self().SDKImpl.AsModuleTypes()\n\tif typeDefsEnabled {'
replace='''\ttypeDefsImpl, typeDefsEnabled := src.Self().SDKImpl.AsModuleTypes()
\tstaticMod, staticUsed, err := s.prototypeStaticTypeScriptTypes(ctx, dag, mod)
\tif err != nil {
\t\treturn nil, err
\t}
\tif staticUsed {
\t\tinitialized = staticMod
\t} else if typeDefsEnabled {'''
assert source.count(needle)==1
source=source.replace(needle,replace)
source=source.replace('\tif !typeDefsEnabled {\n\t\tinitialized, err = s.moduleDefViaRuntime', '\tif !typeDefsEnabled && !staticUsed {\n\t\tinitialized, err = s.moduleDefViaRuntime', 1)
source+='\n'+(out/'helper.go.fragment').read_text()
(out/'modulesource.go').write_text(source)
overlay['Replace'][str(root/'core/schema/modulesource.go')]=str(out/'modulesource.go')
overlay['Replace'][str(root/'core/artifact_batch.go')]=str(out/'artifact_batch.go')
(out/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
print(json.dumps({'workspace':str(app),'input_files':len(inputs),'bytes':sum((mod/p).stat().st_size for p in inputs),'overlay':str(out/'engine-overlay.json')}))
