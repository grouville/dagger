from pathlib import Path
import difflib
import hashlib
import json
import shutil

root=Path(__file__).parent
probe=json.loads((root/'owned-scalar-probe.json').read_text())
assert len(probe)==2 and probe[0]['exit_code']==0 and probe[1]['exit_code']!=0
old=root/'rejected-name-only'
old.mkdir(exist_ok=False)
names=['baseline-objects.go','candidate-objects.go','controlled-objects.go','candidate.patch','engine-overlay.json','engine-validation.json','validation-builds.json','source-identities.json','trivial_scalar_projection_test.go','trivial_scalar_projection_bench_test.go']
for name in names:shutil.copyfile(root/name,old/name)
for name in ['dagger-engine','baseline.test','candidate.test']:
    (root/name).rename(old/name)
helper='''
// Use concrete builtin values: a custom value can advertise Int while owning
// resources. Object, array and custom scalar fields keep their existing paths.
func trivialBuiltinScalar(value Typed) bool {
    switch value := value.(type) {
    case String, Int, Float, Boolean,
         Nullable[String], Nullable[Int], Nullable[Float], Nullable[Boolean]:
        return true
    case DynamicNullable:
        return trivialBuiltinScalar(value.Elem)
    default:
        return false
    }
}
'''
for name in ['baseline-objects.go','candidate-objects.go','controlled-objects.go']:
    path=root/name
    source=path.read_text()
    start=source.index('\n// Scalar accessors return data')
    source=source[:start]+helper
    source=source.replace('trivialBuiltinScalar(astType)','trivialBuiltinScalar(field.Spec.Type)')
    path.write_text(source)
(root/'refinement.json').write_text(json.dumps(dict(reason='The name-only prototype makes a supported reflected resource-owning Int fail with cannot implement OnReleaser. The unchanged policy passes. Match concrete builtin value types and nullable builtin wrappers instead; retain all custom implementations.',variant='concrete-builtin-types',installed_name_only_engine=False,full_command_gain_established=False,prior_component_results='components-exact: name-only prototype, not final production variant',source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['baseline-objects.go','candidate-objects.go','controlled-objects.go']}),indent=2)+'\n')
