package contenthash

import (
	"context"
	"encoding/json"
	digest "github.com/opencontainers/go-digest"
	"net/http"
	"strconv"
	"sync/atomic"
)

var parallelFingerprint atomic.Bool

func TreeFingerprint(ctx context.Context, root string, ignoreContents, reject []string) (digest.Digest, error) {
	if parallelFingerprint.Load() {
		return treeFingerprintParallel(ctx, root, ignoreContents, reject)
	}
	return treeFingerprintSerial(ctx, root, ignoreContents, reject)
}

func ParallelFingerprintDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		parallelFingerprint.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": parallelFingerprint.Load()})
}
