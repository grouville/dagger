package dagql

import (
	"encoding/json"
	"net/http"
	"os"
	"strings"
)

// Diagnostic only: changing representation requires reopening the cache.
var sharedRestoredPostingsEnabled = func() bool {
	data, _ := os.ReadFile("/tmp/shared-restored-postings-mode")
	return strings.TrimSpace(string(data)) != "off"
}()

func SharedRestoredPostingsDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "GET required; mode is read at engine start", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": sharedRestoredPostingsEnabled, "read_at": "engine_start"})
}
