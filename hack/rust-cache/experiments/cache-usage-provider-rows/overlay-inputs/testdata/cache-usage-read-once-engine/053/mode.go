package dagql

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
)

// Diagnostic only. Both arms build the same reverse index at import. Disabled
// mode retains the original class-wide deletion before releasing that index.
var restoredPostingRemovalEnabled atomic.Bool

func init() {
	restoredPostingRemovalEnabled.Store(os.Getenv("DAGGER_DIAGNOSTIC_RESTORED_POSTING_REMOVAL") == "on")
}

func RestoredPostingRemovalDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		restoredPostingRemovalEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": restoredPostingRemovalEnabled.Load()})
}
