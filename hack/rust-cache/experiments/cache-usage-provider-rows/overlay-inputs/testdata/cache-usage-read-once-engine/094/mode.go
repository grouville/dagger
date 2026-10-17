package server

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var spanResourceBatchesEnabled atomic.Bool
var spanResourceBatchesRecording atomic.Bool
var spanResourceBatches atomic.Int64
var spanResourceRows atomic.Int64
var spanResourceEncodings atomic.Int64

func recordSpanResourceBatch(rows, encodings int) {
	if spanResourceBatchesRecording.Load() {
		spanResourceBatches.Add(1)
		spanResourceRows.Add(int64(rows))
		spanResourceEncodings.Add(int64(encodings))
	}
}

func SpanResourceBatchesDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		if value := r.URL.Query().Get("enabled"); value != "" {
			enabled, err := strconv.ParseBool(value)
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			spanResourceBatchesEnabled.Store(enabled)
		}
		if value := r.URL.Query().Get("record"); value != "" {
			record, err := strconv.ParseBool(value)
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			spanResourceBatchesRecording.Store(false)
			spanResourceBatches.Store(0)
			spanResourceRows.Store(0)
			spanResourceEncodings.Store(0)
			spanResourceBatchesRecording.Store(record)
		}
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"enabled": spanResourceBatchesEnabled.Load(), "record": spanResourceBatchesRecording.Load(),
		"batches": spanResourceBatches.Load(), "rows": spanResourceRows.Load(), "encodings": spanResourceEncodings.Load(),
	})
}
