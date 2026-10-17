from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).parent
before=Path('/tmp/rust-cache-sipsma-review/dang-module-blueprint-content-key')
after=Path('/tmp/dang-direct-builtin-receivers')
engine=Path('/tmp/dagger-filesync-snapshot-seeds')
base=Path('/tmp/rust-cache-sipsma-review/cache-usage-minimal-engine')
overlay=json.loads((base/'engine-overlay.json').read_text())
def selected(path):return Path(overlay['Replace'].get(str(path),str(path)))
def method_block(source):
 start=source.index('\t\t\tbuiltinFn := ',source.index('// Register all builtin methods'))
 return source[start:source.index('\n\t\t\tmethodKey := ',start)]
old=method_block((before/'pkg/dang/eval.go').read_text())
current=selected(before/'pkg/dang/eval.go').read_text()
assert current.count(old)==1,'selected engine method registration differs from baseline'
new=method_block((after/'pkg/dang/eval.go').read_text())
# The diagnostic control keeps the original callback body. Both modes share
# the same registration setup; the candidate calls only the receiver callback.
legacy_callback=old[old.index('\t\t\t\tCallFn:'):old.rindex('\n\t\t\t}')]
anchor='\t\t\t\t\tDeprecated:   def.Deprecated,\n'
assert new.count(anchor)==1
new=new.replace(anchor,anchor+legacy_callback,1)
current=current.replace(old,new,1)
(root/'controlled-eval.go').write_text(current)
method=(after/'pkg/dang/builtin_method.go').read_text()
anchor='\treturn m.callReceiver(ctx, m.receiver, args)\n'
assert method.count(anchor)==1
method=method.replace(anchor,'''\tif !directBuiltinReceiverForCall() {
  scope := NewObject(NewType("_temp_", ObjectKind))
  scope.EnterSelf(m.receiver)
  return m.BuiltinFunction.Call(ctx, scope, args)
 }
'''+anchor,1)
(root/'controlled-builtin_method.go').write_text(method)
(root/'mode.go').write_text('''package dang
import (
 "encoding/json"
 "net/http"
 "os"
 "strconv"
 "sync/atomic"
)
// Diagnostic only: no switches or counters are part of the production patch.
var directBuiltinReceivers, directBuiltinReceiverRecord atomic.Bool
var directBuiltinReceiverCalls, scopedBuiltinReceiverCalls atomic.Uint64
func init() { directBuiltinReceivers.Store(os.Getenv("DAGGER_BUILTIN_RECEIVERS_TEST_MODE")=="on") }
func directBuiltinReceiverForCall() bool {
 enabled:=directBuiltinReceivers.Load()
 if directBuiltinReceiverRecord.Load() {
  if enabled { directBuiltinReceiverCalls.Add(1) } else { scopedBuiltinReceiverCalls.Add(1) }
 }
 return enabled
}
func BuiltinReceiverDiagnostic(w http.ResponseWriter,r *http.Request) {
 if r.Method==http.MethodPost {
  enabled,err:=strconv.ParseBool(r.URL.Query().Get("enabled"))
  if err!=nil { http.Error(w,err.Error(),http.StatusBadRequest);return }
  directBuiltinReceivers.Store(enabled)
  if value:=r.URL.Query().Get("record");value!="" {
   record,err:=strconv.ParseBool(value)
   if err!=nil { http.Error(w,err.Error(),http.StatusBadRequest);return }
   directBuiltinReceiverRecord.Store(record)
  }
 } else if r.Method!=http.MethodGet { http.Error(w,"GET or POST required",http.StatusMethodNotAllowed);return }
 w.Header().Set("Content-Type","application/json")
 _=json.NewEncoder(w).Encode(map[string]any{"enabled":directBuiltinReceivers.Load(),"record":directBuiltinReceiverRecord.Load(),"direct_calls":directBuiltinReceiverCalls.Load(),"scoped_calls":scopedBuiltinReceiverCalls.Load()})
}
''')
source=selected(engine/'cmd/engine/debug.go').read_text()
anchor='m.HandleFunc("/debug/usage-sampling", dagql.UsageSamplingDiagnostic)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n\tm.HandleFunc("/debug/builtin-receivers", dang.BuiltinReceiverDiagnostic)',1)
(root/'debug.go').write_text(source)
for name,target in [('eval.go','controlled-eval.go'),('builtin_method.go','controlled-builtin_method.go'),('builtin_receiver_diagnostic.go','mode.go')]:
 overlay['Replace'][str(before/'pkg/dang'/name)]=str(root/target)
for name in ['ast_expressions.go','builtin_receiver_test.go','builtin_receiver_bench_test.go']:
 overlay['Replace'][str(before/'pkg/dang'/name)]=str(after/'pkg/dang'/name)
overlay['Replace'][str(engine/'cmd/engine/debug.go')]=str(root/'debug.go')
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
# Component control is compiled against the same original module as the first
# screen. Engine-specific declaration reuse is tested in the actual engine.
component=json.loads((root/'baseline-tests-overlay.json').read_text())
for name,target in [('eval.go','controlled-eval.go'),('builtin_method.go','controlled-builtin_method.go'),('builtin_receiver_diagnostic.go','mode.go')]:
 if name=='eval.go':
  text=(before/'pkg/dang/eval.go').read_text().replace(old,new,1)
  (root/'controlled-component-eval.go').write_text(text);target='controlled-component-eval.go'
 component['Replace'][str(before/'pkg/dang'/name)]=str(root/target)
component['Replace'][str(before/'pkg/dang/ast_expressions.go')]=str(after/'pkg/dang/ast_expressions.go')
(root/'controlled-component-overlay.json').write_text(json.dumps(component,indent=2)+'\n')
subprocess.run(['/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt','-w',*[str(root/name) for name in ['controlled-eval.go','controlled-component-eval.go','controlled-builtin_method.go','mode.go','debug.go']]],check=True)
(root/'controlled-source-hashes.json').write_text(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['controlled-eval.go','controlled-component-eval.go','controlled-builtin_method.go','mode.go','debug.go']},indent=2)+'\n')
print('Prepared comparison from the selected engine sources; declaration reuse and other existing patches preserved.')
