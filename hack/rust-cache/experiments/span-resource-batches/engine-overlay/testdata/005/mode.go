package core

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var collectionExpansionValuesEnabled atomic.Bool

func CollectionExpansionValuesDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		collectionExpansionValuesEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": collectionExpansionValuesEnabled.Load()})
}
