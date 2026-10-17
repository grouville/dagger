package workspace

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

// A/B control only; excluded from the standalone patch.
var singleTomlParseEnabled atomic.Bool

func SingleTomlParseDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		singleTomlParseEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": singleTomlParseEnabled.Load()})
}
