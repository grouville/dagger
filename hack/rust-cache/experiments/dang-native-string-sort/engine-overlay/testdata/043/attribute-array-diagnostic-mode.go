package clientdb
import (
 "encoding/json"
 "net/http"
 "strconv"
 "sync/atomic"
 "google.golang.org/protobuf/proto"
)
var attributeArrayDecodeEnabled atomic.Bool
func UnmarshalProtoJSONs[T proto.Message](pb []byte, base T, out *[]T) error {
 if attributeArrayDecodeEnabled.Load() { return unmarshalProtoJSONsOptimized(pb, base, out) }
 return unmarshalProtoJSONsLegacy(pb, base, out)
}
func AttributeArrayDecodeDiagnostic(w http.ResponseWriter, r *http.Request) {
 if r.Method == http.MethodPost {
  enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
  if err != nil { http.Error(w, err.Error(), http.StatusBadRequest); return }
  attributeArrayDecodeEnabled.Store(enabled)
 } else if r.Method != http.MethodGet { http.Error(w,"GET or POST required",http.StatusMethodNotAllowed);return }
 w.Header().Set("Content-Type","application/json")
 _ = json.NewEncoder(w).Encode(map[string]bool{"enabled":attributeArrayDecodeEnabled.Load()})
}
