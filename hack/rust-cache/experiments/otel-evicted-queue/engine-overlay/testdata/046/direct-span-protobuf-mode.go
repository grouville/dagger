package clientdb

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"

	telemetry "github.com/dagger/otel-go"
	tracepb "go.opentelemetry.io/proto/otlp/trace/v1"
)

var directSpanPB atomic.Bool

func ForwardSpansToPB(rows []Span) []*tracepb.ResourceSpans {
	if directSpanPB.Load() {
		return SpansToPB(rows)
	}
	return telemetry.SpansToPB(ReadOnlySpans(rows))
}

func DirectSpanPBDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		directSpanPB.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": directSpanPB.Load()})
}
