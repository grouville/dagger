from pathlib import Path
import hashlib,json,shutil,subprocess

base=Path('/tmp/rust-cache-sipsma-review');root=base/'small-proto-fields';root.mkdir(exist_ok=False)
protobuf=Path('/tmp/protobuf-field-order-experiment');source=Path('/tmp/dagger-filesync-snapshot-seeds');previous=base/'parallel-fingerprint-engine'
before=(protobuf/'internal/order/range.go').read_text()
installed=Path('/home/dagger/go/pkg/mod/google.golang.org/protobuf@v1.36.11/internal/order/range.go').read_text()
assert before==installed
sort_fields='\tsort.Slice(fields, func(i, j int) bool {\n\t\treturn less(fields[i].fd, fields[j].fd)\n\t})'
assert before.count(sort_fields)==1
small=before.replace(sort_fields,'''\tswitch len(fields) {
    case 0, 1:
    case 2:
        if less(fields[1].fd, fields[0].fd) { fields[0], fields[1] = fields[1], fields[0] }
    default:
        sort.Slice(fields, func(i, j int) bool { return less(fields[i].fd, fields[j].fd) })
    }''')
(root/'before.go').write_text(before);(root/'candidate.go').write_text(small)
needle='switch len(fields) {';assert small.count(needle)==1
controlled=small.replace(needle,'switch {').replace('case 0, 1:', 'case len(fields) <= 1 && smallFields.Load():').replace('case 2:', 'case len(fields) == 2 && smallFields.Load():')
(root/'controlled.go').write_text(controlled)
(root/'order_mode.go').write_text('''package order
import "sync/atomic"
var smallFields atomic.Bool
func SetSmallFieldsDiagnostic(enabled bool) { smallFields.Store(enabled) }
func SmallFieldsDiagnosticEnabled() bool { return smallFields.Load() }
''')
(root/'json_mode.go').write_text('''package protojson
import "google.golang.org/protobuf/internal/order"
func SetSmallFieldsDiagnostic(enabled bool) { order.SetSmallFieldsDiagnostic(enabled) }
func SmallFieldsDiagnosticEnabled() bool { return order.SmallFieldsDiagnosticEnabled() }
''')
for pkg,name in [('internal/order','order'),('encoding/protojson','protojson_test'),('encoding/prototext','prototext_test'),('proto','proto_test')]:
    label=pkg.replace('/','_')+'_mode_test.go'
    body='''import (
    "os"
    "google.golang.org/protobuf/internal/order"
)
func init() { order.SetSmallFieldsDiagnostic(os.Getenv("DAGGER_TEST_SMALL_PROTO_FIELDS")=="1") }
'''
    if name=='order':body='''import "os"
func init() { SetSmallFieldsDiagnostic(os.Getenv("DAGGER_TEST_SMALL_PROTO_FIELDS")=="1") }
'''
    (root/label).write_text('package '+name+'\n'+body)
(root/'clientdb_mode_test.go').write_text('''package clientdb
import (
    "os"
    "google.golang.org/protobuf/encoding/protojson"
)
func init() { protojson.SetSmallFieldsDiagnostic(os.Getenv("DAGGER_TEST_SMALL_PROTO_FIELDS")=="1") }
''')
overlay=json.loads((previous/'overlay.json').read_text())
for logical,item in json.loads((previous/'manifest.json').read_text()).items():assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest()==item['sha256'],logical
for name in ['engine.go.mod','engine.go.sum']:shutil.copyfile(previous/name,root/name)
with (root/'engine.go.mod').open('a') as stream:stream.write('\nreplace google.golang.org/protobuf => '+str(protobuf)+'\n')
debug=Path(overlay['Replace'][str(source/'cmd/engine/debug.go')]).read_text()
assert debug.count('"net/http/pprof"')==1
debug=debug.replace('"net/http/pprof"','"net/http/pprof"\n    "google.golang.org/protobuf/encoding/protojson"')
assert debug.count('m := http.NewServeMux()')==1
debug=debug.replace('m := http.NewServeMux()','''m := http.NewServeMux()
    m.HandleFunc("/debug/small-proto-fields", func(w http.ResponseWriter,r *http.Request) {
        if r.Method==http.MethodPost {
            enabled,err:=strconv.ParseBool(r.URL.Query().Get("enabled"))
            if err!=nil {http.Error(w,err.Error(),400);return};protojson.SetSmallFieldsDiagnostic(enabled)
        } else if r.Method!=http.MethodGet {http.Error(w,"GET or POST required",405);return}
        w.Header().Set("Content-Type","application/json")
        _=json.NewEncoder(w).Encode(map[string]bool{"enabled":protojson.SmallFieldsDiagnosticEnabled()})
    })''')
(root/'debug.go').write_text(debug)
updates={
    str(protobuf/'internal/order/range.go'):str(root/'controlled.go'),
    str(protobuf/'internal/order/small_fields_mode.go'):str(root/'order_mode.go'),
    str(protobuf/'encoding/protojson/small_fields_mode.go'):str(root/'json_mode.go'),
    str(protobuf/'internal/order/small_fields_reference_test.go'):str(root/'order_test.go'),
    str(protobuf/'encoding/protojson/small_fields_compat_test.go'):str(root/'json_test.go'),
    str(source/'engine/clientdb/small_fields_mode_test.go'):str(root/'clientdb_mode_test.go'),
    str(source/'cmd/engine/debug.go'):str(root/'debug.go'),
}
for pkg in ['internal/order','encoding/protojson','encoding/prototext','proto']:updates[str(protobuf/pkg/'small_fields_init_test.go')]=str(root/(pkg.replace('/','_')+'_mode_test.go'))
bench=(protobuf/'internal/order/range_bench_test.go').read_text().replace('for b.Loop() {','for i := 0; i < b.N; i++ {')
(root/'range_bench_test.go').write_text(bench)
updates[str(protobuf/'internal/order/range_bench_test.go')]=str(root/'range_bench_test.go')
overlay['Replace'].update(updates)
(root/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
subprocess.run(['gofmt','-w',*[str(p) for p in root.glob('*.go')]],check=True)
(root/'provenance.json').write_text(json.dumps(dict(base_engine_sha256='f73ec4d9aa78b158551fb2c2bbbc1247c0973a9c8d725442b5babaae6e2b1721',protobuf_version='v1.36.11',upstream_source='https://github.com/protocolbuffers/protobuf-go/blob/master/internal/order/range.go',module_go='1.23',small_message_only=True,larger_message_sort_unchanged=True,map_sort_unchanged=True,default_enabled=False,scope='Diagnostic switch for the existing zero/one/two-field prototype; production candidate has no switch or new public API.'),indent=2)+'\n')
print(root)
