package dagql

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var interfaceCandidatePruningEnabled atomic.Bool

func InterfaceCandidatePruningDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		interfaceCandidatePruningEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", 405)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": interfaceCandidatePruningEnabled.Load()})
}
