package core

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var collectionExpansionLimit atomic.Int64
var collectionExpansionActive atomic.Int64
var collectionExpansionPeak atomic.Int64
var collectionExpansionStarted atomic.Int64

func CollectionExpansionLimitDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		limit, err := strconv.ParseInt(r.URL.Query().Get("limit"), 10, 64)
		if err != nil || limit < 0 || limit > 4096 {
			http.Error(w, "limit must be between 0 and 4096", 400)
			return
		}
		if collectionExpansionActive.Load() != 0 {
			http.Error(w, "collection expansion is active", 409)
			return
		}
		collectionExpansionLimit.Store(limit)
		collectionExpansionPeak.Store(0)
		collectionExpansionStarted.Store(0)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", 405)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]int64{
		"limit": collectionExpansionLimit.Load(), "active": collectionExpansionActive.Load(),
		"peak": collectionExpansionPeak.Load(), "started": collectionExpansionStarted.Load(),
	})
}
