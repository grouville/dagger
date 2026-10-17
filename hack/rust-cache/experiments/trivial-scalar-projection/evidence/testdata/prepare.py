from pathlib import Path
import difflib
import hashlib
import json

root = Path(__file__).parent
work = Path('/tmp/dagger-compaction-ownership-only')
engine = Path('/tmp/dagger-filesync-snapshot-seeds')

def adapt(original, enabled):
    needle = '\t\tDoNotCache:           field.Spec.DoNotCache != "",'
    assert original.count(needle) == 1
    suffix = ' || (field.Spec.Trivial && sel.Nth == 0 && trivialBuiltinScalar(astType))' if enabled else ''
    return original.replace(needle, '\t\tDoNotCache:           field.Spec.DoNotCache != ""' + suffix + ',')

helper = '''
// Scalar accessors return data already held by their receiver. Keep object,
// array, enum and custom scalar results on their existing attachment paths.
func trivialBuiltinScalar(typ *ast.Type) bool {
    if typ == nil || typ.Elem != nil { return false }
    switch typ.NamedType {
    case "String", "Int", "Float", "Boolean": return true
    default: return false
    }
}
'''
for arm, enabled in [('baseline', False), ('candidate', True)]:
    original = (work/'dagql/objects.go').read_text()
    source = adapt(original, enabled) + helper
    path = root/(arm+'-objects.go')
    path.write_text(source)
    overlay = {'Replace': {str(work/'dagql/objects.go'):str(path)}}
    for name in ['trivial_scalar_projection_test.go', 'trivial_scalar_projection_bench_test.go']:
        overlay['Replace'][str(work/'dagql'/name)] = str(root/name)
    (root/(arm+'-overlay.json')).write_text(json.dumps(overlay,indent=2)+'\n')
    if enabled:
        (root/'candidate.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),source.splitlines(True),fromfile='a/dagql/objects.go',tofile='b/dagql/objects.go')))

source = (engine/'dagql/objects.go').read_text()
needle = '\t\tDoNotCache:           field.Spec.DoNotCache != "",'
assert source.count(needle) == 1
source = source.replace(needle, '\t\tDoNotCache:           field.Spec.DoNotCache != "" || (directTrivialScalarFields.Load() && field.Spec.Trivial && sel.Nth == 0 && trivialBuiltinScalar(astType)),') + helper
(root/'controlled-objects.go').write_text(source)
overlay = json.loads(Path('/tmp/rust-cache-sipsma-review/config-content-declarations/engine-overlay.json').read_text())
assert str(engine/'dagql/objects.go') not in overlay['Replace']
overlay['Replace'][str(engine/'dagql/objects.go')] = str(root/'controlled-objects.go')
overlay['Replace'][str(engine/'dagql/trivial_scalar_projection_mode.go')] = str(root/'mode.go')
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
(root/'source-identities.json').write_text(json.dumps(dict(upstream='ff0b029a4d270a651b9a8c7286babc79089066e4',selected_engine_sha256='51542ef941c4e3bd96c2ce770c118d154824272ff247d8b9038b0cb27e5fa0e3',selected_overlay_sha256=hashlib.sha256(Path('/tmp/rust-cache-sipsma-review/config-content-declarations/engine-overlay.json').read_bytes()).hexdigest(),production_scope='Use the existing uncached path only for Trivial fields whose selected return type is a builtin scalar. Ordinary functions, object fields, arrays, enums and custom scalar fields retain existing policies.'),indent=2)+'\n')
