package dagql
import (
 "encoding/json"
 "net/http"
 "strconv"
 "sync/atomic"
)
var snapshotCompletionFast atomic.Bool
var snapshotCompletionRecord atomic.Bool
var snapshotCompletionCalls atomic.Uint64
var snapshotCompletionSkipped atomic.Uint64
func SnapshotCompletionDiagnostic(w http.ResponseWriter,r *http.Request) {
 if r.Method == http.MethodPost {
  enabled,err:=strconv.ParseBool(r.URL.Query().Get("enabled"));if err!=nil {http.Error(w,err.Error(),400);return}
  snapshotCompletionFast.Store(enabled)
  snapshotCompletionRecord.Store(r.URL.Query().Get("record")=="true")
  snapshotCompletionCalls.Store(0);snapshotCompletionSkipped.Store(0)
 } else if r.Method != http.MethodGet {http.Error(w,"GET or POST required",405);return}
 w.Header().Set("Content-Type","application/json")
 _=json.NewEncoder(w).Encode(map[string]any{"enabled":snapshotCompletionFast.Load(),"record":snapshotCompletionRecord.Load(),"calls":snapshotCompletionCalls.Load(),"skipped":snapshotCompletionSkipped.Load()})
}
