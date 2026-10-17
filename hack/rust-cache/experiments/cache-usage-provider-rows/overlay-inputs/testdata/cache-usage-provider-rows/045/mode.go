package dagql

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var usagePrunePreflightEnabled atomic.Bool
var usagePruneShortcuts, usagePruneSnapshots atomic.Uint64
var usagePruneMeasuredBytes atomic.Int64

type usagePrunePreflightKey struct{}

func usagePrunePreflightFor(ctx context.Context) bool {
	if enabled, ok := ctx.Value(usagePrunePreflightKey{}).(bool); ok {
		return enabled
	}
	return usagePrunePreflightEnabled.Load()
}
func usagePrunePreflightContext(ctx context.Context) context.Context {
	return context.WithValue(ctx, usagePrunePreflightKey{}, usagePrunePreflightFor(ctx))
}
func UsagePrunePreflightDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		usagePrunePreflightEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": usagePrunePreflightEnabled.Load(), "no_target_passes": usagePruneShortcuts.Load(), "full_snapshots": usagePruneSnapshots.Load(), "last_nonblob_measured_bytes": usagePruneMeasuredBytes.Load()})
}
