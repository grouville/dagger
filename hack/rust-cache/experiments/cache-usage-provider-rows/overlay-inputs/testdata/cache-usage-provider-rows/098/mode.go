package server

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var telemetryFlushCoalescingEnabled atomic.Bool
var telemetryFlushRequests, telemetryFlushExecutions, telemetryClientFlushes atomic.Uint64

func TelemetryFlushCoalescingDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		telemetryFlushCoalescingEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"enabled":        telemetryFlushCoalescingEnabled.Load(),
		"requests":       telemetryFlushRequests.Load(),
		"executions":     telemetryFlushExecutions.Load(),
		"client_flushes": telemetryClientFlushes.Load(),
	})
}
