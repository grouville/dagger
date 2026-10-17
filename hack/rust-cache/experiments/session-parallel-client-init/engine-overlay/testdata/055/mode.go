package clientdb

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var spanLookupFast atomic.Bool
var spanLookupRecording atomic.Bool
var spanLookupRows atomic.Int64
var spanLookupNewParentComparisons atomic.Int64

func SpanLookupFanoutDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		if text := r.URL.Query().Get("enabled"); text != "" {
			enabled, err := strconv.ParseBool(text)
			if err != nil {
				http.Error(w, err.Error(), 400)
				return
			}
			spanLookupFast.Store(enabled)
		}
		if text := r.URL.Query().Get("record"); text != "" {
			record, err := strconv.ParseBool(text)
			if err != nil {
				http.Error(w, err.Error(), 400)
				return
			}
			spanLookupRecording.Store(false)
			spanLookupRows.Store(0)
			spanLookupNewParentComparisons.Store(0)
			spanLookupRecording.Store(record)
		}
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", 405)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": spanLookupFast.Load(), "record": spanLookupRecording.Load(), "rows": spanLookupRows.Load(), "new_parent_scan_comparisons": spanLookupNewParentComparisons.Load()})
}
