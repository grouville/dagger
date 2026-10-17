package dang

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
)

// Diagnostic only: no switches or counters are part of the production patch.
var directBuiltinReceivers, directBuiltinReceiverRecord atomic.Bool
var directBuiltinReceiverCalls, scopedBuiltinReceiverCalls atomic.Uint64

func init() { directBuiltinReceivers.Store(os.Getenv("DAGGER_BUILTIN_RECEIVERS_TEST_MODE") == "on") }
func directBuiltinReceiverForCall() bool {
	enabled := directBuiltinReceivers.Load()
	if directBuiltinReceiverRecord.Load() {
		if enabled {
			directBuiltinReceiverCalls.Add(1)
		} else {
			scopedBuiltinReceiverCalls.Add(1)
		}
	}
	return enabled
}
func BuiltinReceiverDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		directBuiltinReceivers.Store(enabled)
		if value := r.URL.Query().Get("record"); value != "" {
			record, err := strconv.ParseBool(value)
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			directBuiltinReceiverRecord.Store(record)
		}
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": directBuiltinReceivers.Load(), "record": directBuiltinReceiverRecord.Load(), "direct_calls": directBuiltinReceiverCalls.Load(), "scoped_calls": scopedBuiltinReceiverCalls.Load()})
}
