package schema

import (
	"context"
	"encoding/json"
	"net/http"
	"strconv"
	"sync/atomic"

	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
)

var dimensionKeyFieldsDirect atomic.Bool

func installDimensionKeyFieldsDiagnostic(srv *dagql.Server) {
	class := srv.InstallObject(dagql.NewClass[*core.ArtifactDimensionKey](srv)).(dagql.Class[*core.ArtifactDimensionKey])
	for _, name := range []string{"dimension", "key"} {
		field, ok := class.Field(name, "")
		if !ok {
			panic("missing dimension-key field: " + name)
		}
		field.Spec.DoNotCache = ""
		field.Spec.GetDynamicInput = func(_ context.Context, _ dagql.AnyResult, _ map[string]dagql.Input, _ call.View, req *dagql.CallRequest) error {
			req.DoNotCache = dimensionKeyFieldsDirect.Load()
			return nil
		}
	}
}

func DimensionKeyFieldsDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		dimensionKeyFieldsDirect.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": dimensionKeyFieldsDirect.Load()})
}
