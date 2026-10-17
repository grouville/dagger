package dagql

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

// Diagnostic-only comparison. The production patch has no switch or endpoint.
var usageSamplingEnabled atomic.Bool

type usageSamplingKey struct{}

func usageSamplingFor(ctx context.Context) bool {
	if enabled, ok := ctx.Value(usageSamplingKey{}).(bool); ok {
		return enabled
	}
	return usageSamplingEnabled.Load()
}
func usageSamplingContext(ctx context.Context) context.Context {
	return context.WithValue(ctx, usageSamplingKey{}, usageSamplingFor(ctx))
}
func UsageSamplingDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		usageSamplingEnabled.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": usageSamplingEnabled.Load()})
}
