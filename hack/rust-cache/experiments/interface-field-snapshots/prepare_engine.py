from pathlib import Path
import hashlib
import json

root=Path(__file__).parent;base=root.parent
source=Path('/tmp/dagger-filesync-snapshot-seeds')
upstream=Path('/tmp/dagger-interface-field-snapshots-upstream')
overlay=json.loads((base/'layercopy-known-dirs/engine-overlay.json').read_text())
server=Path(overlay['Replace'][str(source/'dagql/server.go')]).read_text()
def function(s):
    start=s.index('func (s *Server) reconcileInterfaceImplsLocked(')
    return s[start:s.index('\n}\n',start)+3]
original=function(server)
optimized=function((upstream/'dagql/server.go').read_text())
controlled=server.replace(original,optimized.replace(') reconcileInterfaceImplsLocked(',') reconcileInterfaceImplsOptimized(',1))
controlled+='\n'+original.replace(') reconcileInterfaceImplsLocked(',') reconcileInterfaceImplsOriginal(',1)+"""
func (s *Server) reconcileInterfaceImplsLocked(view call.View) {
    if interfaceFieldSnapshotsFast.Load() {s.reconcileInterfaceImplsOptimized(view)} else {s.reconcileInterfaceImplsOriginal(view)}
}
"""
(root/'controlled-server.go').write_text(controlled)
interfaces=(upstream/'dagql/interfaces.go').read_text();start=interfaces.index('func satisfiesInterfaceFields(')
helper=interfaces[start:interfaces.index('\n}\n',start)+3]
(root/'mode.go').write_text("""package dagql
import (
 "encoding/json"
 "net/http"
 "strconv"
 "sync/atomic"
 "github.com/dagger/dagger/dagql/call"
)
var interfaceFieldSnapshotsFast atomic.Bool
func InterfaceFieldSnapshotsDiagnostic(w http.ResponseWriter,r *http.Request) {
 if r.Method==http.MethodPost {
  enabled,err:=strconv.ParseBool(r.URL.Query().Get("enabled"));if err!=nil {http.Error(w,err.Error(),400);return}
  interfaceFieldSnapshotsFast.Store(enabled)
 } else if r.Method!=http.MethodGet {http.Error(w,"GET or POST required",405);return}
 w.Header().Set("Content-Type","application/json")
 _=json.NewEncoder(w).Encode(map[string]bool{"enabled":interfaceFieldSnapshotsFast.Load()})
}
"""+helper)
debug=Path(overlay['Replace'][str(source/'cmd/engine/debug.go')]).read_text()
needle='m := http.NewServeMux()';assert debug.count(needle)==1
debug=debug.replace(needle,needle+'\n m.HandleFunc("/debug/interface-field-snapshots",dagql.InterfaceFieldSnapshotsDiagnostic)')
(root/'debug.go').write_text(debug)
overlay['Replace'][str(source/'dagql/server.go')]=str(root/'controlled-server.go')
overlay['Replace'][str(source/'dagql/interface_field_snapshots_mode.go')]=str(root/'mode.go')
overlay['Replace'][str(source/'cmd/engine/debug.go')]=str(root/'debug.go')
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
for extension in ['mod','sum']:
    path=base/'layercopy-known-dirs'/('engine.go.'+extension)
    if path.exists():(root/path.name).write_bytes(path.read_bytes())
print('Prepared same-binary A/B; interface snapshot reuse defaults OFF.')
