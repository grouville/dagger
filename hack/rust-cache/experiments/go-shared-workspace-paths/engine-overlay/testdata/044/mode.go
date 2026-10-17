package dagql

import (
	"encoding/json"
	"github.com/dagger/dagger/dagql/call"
	"net/http"
	"strconv"
	"sync/atomic"
)

var interfaceFieldSnapshotsFast atomic.Bool

func InterfaceFieldSnapshotsDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		interfaceFieldSnapshotsFast.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", 405)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": interfaceFieldSnapshotsFast.Load()})
}
func satisfiesInterfaceFields(fields []FieldSpec, fieldSpec func(string, call.View) (FieldSpec, bool), view call.View, checker ImplementsChecker) bool {
	for _, ifaceField := range fields {
		objField, ok := fieldSpec(ifaceField.Name, view)
		if !ok {
			return false
		}
		if !typeCompatible(ifaceField.Type.Type(), objField.Type.Type(), checker) {
			return false
		}
		if !argsCompatible(ifaceField.Args, objField.Args, view, checker) {
			return false
		}
	}
	return true
}
