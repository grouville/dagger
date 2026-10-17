package engineutil

import (
	"encoding/json"
	"github.com/dagger/dagger/engine"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
)

// Diagnostics only; excluded from the production patch.
var moduleHostStatReadEnabled, moduleHostStatReadRecord atomic.Bool
var moduleHostCombined, moduleHostStatOnly, moduleHostReadOnly atomic.Uint64

func init() {
	moduleHostStatReadEnabled.Store(os.Getenv("DAGGER_MODULE_HOST_STAT_READ_TEST_MODE") == "on")
}
func ModuleHostStatReadEnabled() bool { return moduleHostStatReadEnabled.Load() }
func recordModuleHostStatRead(opts engine.LocalImportOpts) {
	if !moduleHostStatReadRecord.Load() {
		return
	}
	if opts.StatPathOnly && opts.ReadSingleFileOnly {
		moduleHostCombined.Add(1)
	} else if opts.StatPathOnly {
		moduleHostStatOnly.Add(1)
	} else if opts.ReadSingleFileOnly {
		moduleHostReadOnly.Add(1)
	}
}
func ModuleHostStatReadDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		moduleHostStatReadEnabled.Store(enabled)
		if raw := r.URL.Query().Get("record"); raw != "" {
			record, err := strconv.ParseBool(raw)
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			moduleHostStatReadRecord.Store(record)
		}
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": moduleHostStatReadEnabled.Load(), "record": moduleHostStatReadRecord.Load(), "combined": moduleHostCombined.Load(), "stat_only": moduleHostStatOnly.Load(), "read_only": moduleHostReadOnly.Load()})
}
