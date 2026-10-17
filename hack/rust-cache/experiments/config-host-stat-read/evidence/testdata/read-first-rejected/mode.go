package core

import (
	"context"
	"encoding/json"
	fstypes "github.com/dagger/dagger/internal/fsutil/types"
	"net/http"
	"os"
	"strconv"
	"sync/atomic"
)

// Experiment only: production has no switches or counters.
var moduleHostReadFirstEnabled, moduleHostReadFirstRecord atomic.Bool
var moduleHostReads, moduleHostStats atomic.Uint64

func init() {
	moduleHostReadFirstEnabled.Store(os.Getenv("DAGGER_MODULE_HOST_READ_FIRST_TEST_MODE") == "on")
}
func moduleHostRead(ctx context.Context, client moduleHostFileClient, path string) ([]byte, error) {
	if moduleHostReadFirstRecord.Load() {
		moduleHostReads.Add(1)
	}
	return client.ReadCallerHostFile(ctx, path)
}
func moduleHostStat(ctx context.Context, client moduleHostFileClient, path string) (*fstypes.Stat, error) {
	if moduleHostReadFirstRecord.Load() {
		moduleHostStats.Add(1)
	}
	return client.StatCallerHostPath(ctx, path, false)
}
func ModuleHostReadFirstDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		moduleHostReadFirstEnabled.Store(enabled)
		if raw := r.URL.Query().Get("record"); raw != "" {
			record, err := strconv.ParseBool(raw)
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			moduleHostReadFirstRecord.Store(record)
		}
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": moduleHostReadFirstEnabled.Load(), "record": moduleHostReadFirstRecord.Load(), "reads": moduleHostReads.Load(), "stats": moduleHostStats.Load()})
}
