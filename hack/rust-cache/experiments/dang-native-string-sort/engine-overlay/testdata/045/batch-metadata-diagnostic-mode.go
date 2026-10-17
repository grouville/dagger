package clientdb

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var batchMetadataFast atomic.Bool
var batchMetadataRecord atomic.Bool
var batchMetadataSpanRows atomic.Uint64
var batchMetadataLogRows atomic.Uint64
var batchMetadataResources atomic.Uint64
var batchMetadataScopes atomic.Uint64

func BatchMetadataEnabled() bool { return batchMetadataFast.Load() }

func recordSpanBatchMetadata(rows, resources, scopes int) {
	if batchMetadataRecord.Load() {
		batchMetadataSpanRows.Add(uint64(rows))
		batchMetadataResources.Add(uint64(resources))
		batchMetadataScopes.Add(uint64(scopes))
	}
}

func recordLogBatchMetadata(rows, resources, scopes int) {
	if batchMetadataRecord.Load() {
		batchMetadataLogRows.Add(uint64(rows))
		batchMetadataResources.Add(uint64(resources))
		batchMetadataScopes.Add(uint64(scopes))
	}
}

func BatchMetadataDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		batchMetadataFast.Store(enabled)
		batchMetadataRecord.Store(r.URL.Query().Get("record") == "true")
		batchMetadataSpanRows.Store(0)
		batchMetadataLogRows.Store(0)
		batchMetadataResources.Store(0)
		batchMetadataScopes.Store(0)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{
		"enabled": batchMetadataFast.Load(), "record": batchMetadataRecord.Load(),
		"span_rows": batchMetadataSpanRows.Load(), "log_rows": batchMetadataLogRows.Load(),
		"resource_decodes": batchMetadataResources.Load(), "scope_decodes": batchMetadataScopes.Load(),
	})
}
