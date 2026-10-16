from pathlib import Path
import hashlib,json,subprocess

root=Path(__file__).parent;base=root.parent;source=Path('/tmp/dagger-filesync-snapshot-seeds')
overlay=json.loads((root/'overlay.json').read_text())
before=(root/'before.go').read_text();after=(root/'after.go').read_text()
start=before.index('func (l *spanLookup) addLocked(');end=before.index('\n// Marker byte strings',start)
original=before[start:end].replace('func (l *spanLookup) addLocked(','func (l *spanLookup) addLockedOriginal(',1)
controlled=after.replace('func (l *spanLookup) addLocked(','func (l *spanLookup) addLockedOptimized(',1)
controlled+='\n'+original+'\n'+'''func (l *spanLookup) addLocked(row Span, targets []string) {
    if spanLookupRecording.Load() {
        spanLookupRows.Add(1)
        if row.ParentSpanID.Valid {
            if _,seen:=l.firstRow[spanLookupKey{traceID:row.TraceID,spanID:row.SpanID}];!seen {
                if _,known:=l.parent[row.SpanID];!known {
                    spanLookupNewParentComparisons.Add(int64(len(l.children[row.ParentSpanID.String])))
                }
            }
        }
    }
    if spanLookupFast.Load() {l.addLockedOptimized(row,targets)} else {l.addLockedOriginal(row,targets)}
}
'''
(root/'controlled.go').write_text(controlled)
(root/'mode.go').write_text('''package clientdb
import (
 "encoding/json"
 "net/http"
 "strconv"
 "sync/atomic"
)
var spanLookupFast atomic.Bool
var spanLookupRecording atomic.Bool
var spanLookupRows atomic.Int64
var spanLookupNewParentComparisons atomic.Int64
func SpanLookupFanoutDiagnostic(w http.ResponseWriter,r *http.Request) {
 if r.Method==http.MethodPost {
  if text:=r.URL.Query().Get("enabled");text!="" {
   enabled,err:=strconv.ParseBool(text);if err!=nil {http.Error(w,err.Error(),400);return};spanLookupFast.Store(enabled)
  }
  if text:=r.URL.Query().Get("record");text!="" {
   record,err:=strconv.ParseBool(text);if err!=nil {http.Error(w,err.Error(),400);return}
   spanLookupRecording.Store(false);spanLookupRows.Store(0);spanLookupNewParentComparisons.Store(0);spanLookupRecording.Store(record)
  }
 } else if r.Method!=http.MethodGet {http.Error(w,"GET or POST required",405);return}
 w.Header().Set("Content-Type","application/json")
 _=json.NewEncoder(w).Encode(map[string]any{"enabled":spanLookupFast.Load(),"record":spanLookupRecording.Load(),"rows":spanLookupRows.Load(),"new_parent_scan_comparisons":spanLookupNewParentComparisons.Load()})
}
''')
debug=Path(overlay['Replace'][str(source/'cmd/engine/debug.go')]).read_text()
assert debug.count('m := http.NewServeMux()')==1
debug=debug.replace('m := http.NewServeMux()','m := http.NewServeMux()\n m.HandleFunc("/debug/span-lookup-fanout",clientdb.SpanLookupFanoutDiagnostic)')
if '"github.com/dagger/dagger/engine/clientdb"' not in debug:debug=debug.replace('import (','import (\n "github.com/dagger/dagger/engine/clientdb"',1)
(root/'debug.go').write_text(debug)
overlay['Replace'][str(source/'engine/clientdb/telemetry_store.go')]=str(root/'controlled.go')
overlay['Replace'][str(source/'engine/clientdb/span_lookup_fanout_mode.go')]=str(root/'mode.go')
overlay['Replace'][str(source/'cmd/engine/debug.go')]=str(root/'debug.go')
subprocess.run(['gofmt','-w',*[str(root/f) for f in ['controlled.go','mode.go','debug.go']]],check=True)
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
(root/'manifest.json').write_text(json.dumps({logical:dict(replacement=p,sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest()) for logical,p in overlay['Replace'].items()},indent=2)+'\n')
print('Reversible index changes prepared; comparison counter off outside diagnostics')
