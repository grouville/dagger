//go:build linux

package layercopy

import (
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"
)

var knownDirsFast atomic.Bool
var knownDirsRecording atomic.Bool
var knownDirsCalls atomic.Int64
var knownDirsHits atomic.Int64

func KnownDirectoriesDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		if text := r.URL.Query().Get("enabled"); text != "" {
			enabled, err := strconv.ParseBool(text)
			if err != nil {
				http.Error(w, err.Error(), 400)
				return
			}
			knownDirsFast.Store(enabled)
		}
		if text := r.URL.Query().Get("record"); text != "" {
			record, err := strconv.ParseBool(text)
			if err != nil {
				http.Error(w, err.Error(), 400)
				return
			}
			knownDirsRecording.Store(false)
			knownDirsCalls.Store(0)
			knownDirsHits.Store(0)
			knownDirsRecording.Store(record)
		}
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", 405)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"enabled": knownDirsFast.Load(), "record": knownDirsRecording.Load(), "ensure_calls": knownDirsCalls.Load(), "known_overwrite_calls": knownDirsHits.Load()})
}
