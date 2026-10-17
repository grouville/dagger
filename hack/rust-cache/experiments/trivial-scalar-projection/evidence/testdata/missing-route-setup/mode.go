package dagql

import (
	"encoding/json"
	"net/http"
	"sync/atomic"
)

var directTrivialScalarFields atomic.Bool

func init() {
	http.HandleFunc("/debug/trivial-scalar-fields", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			directTrivialScalarFields.Store(r.URL.Query().Get("enabled") == "true")
		}
		_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": directTrivialScalarFields.Load()})
	})
}
