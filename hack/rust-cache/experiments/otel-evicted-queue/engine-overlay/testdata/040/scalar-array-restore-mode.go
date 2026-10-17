package dagql

import (
	"bytes"
	"encoding/json"
	"net/http"
	"os"
)

// Read once before restoring the cache. Changing this file requires a restart:
// already-decoded values retain their current representation.
var scalarArrayRestoreEnabled = func() bool {
	value, err := os.ReadFile("/tmp/scalar-array-restore-mode")
	return err == nil && bytes.Equal(bytes.TrimSpace(value), []byte("on"))
}()

func ScalarArrayRestoreDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "GET required; mode is read at engine startup", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": scalarArrayRestoreEnabled, "read_at": "engine_start"})
}
