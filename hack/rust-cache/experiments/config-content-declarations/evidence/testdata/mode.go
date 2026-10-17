package workspace

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
)

// Experiment controls only; excluded from the standalone patch.
var configDeclarationsEnabled, configDeclarationsRecord atomic.Bool
var configDeclarationLookups, configDeclarationParses, configDeclarationControls atomic.Uint64

func init() {
	configDeclarationsEnabled.Store(os.Getenv("DAGGER_CONFIG_DECLARATIONS_TEST_MODE") == "on")
}
func ConfigDeclarationsDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		configDeclarationsEnabled.Store(enabled)
		if raw := r.URL.Query().Get("record"); raw != "" {
			record, err := strconv.ParseBool(raw)
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			configDeclarationsRecord.Store(record)
		}
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": configDeclarationsEnabled.Load(), "record": configDeclarationsRecord.Load(), "lookups": configDeclarationLookups.Load(), "parses": configDeclarationParses.Load(), "control_calls": configDeclarationControls.Load(), "entries": gitClientConfigCache.Len()})
}
