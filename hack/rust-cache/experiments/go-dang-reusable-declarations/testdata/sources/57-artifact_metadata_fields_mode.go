package schema

import (
	"context"
	"encoding/json"
	"github.com/dagger/dagger/core"
	"github.com/dagger/dagger/dagql"
	"github.com/dagger/dagger/dagql/call"
	"net/http"
	"strconv"
	"sync/atomic"
)

var artifactMetadataDirect atomic.Bool

func installArtifactMetadataFieldsDiagnostic(srv *dagql.Server) {
	object, ok := srv.ObjectType("Artifact")
	if !ok {
		panic("missing Artifact")
	}
	class := object.(dagql.Class[*core.Artifact])
	for _, name := range []string{"description", "uri"} {
		field, ok := class.Field(name, "")
		if !ok {
			panic("missing artifact metadata field: " + name)
		}
		field.Spec.DoNotCache = ""
		field.Spec.GetDynamicInput = func(_ context.Context, _ dagql.AnyResult, _ map[string]dagql.Input, _ call.View, req *dagql.CallRequest) error {
			req.DoNotCache = artifactMetadataDirect.Load()
			return nil
		}
	}
}
func ArtifactMetadataFieldsDiagnostic(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodPost {
		enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		artifactMetadataDirect.Store(enabled)
	} else if r.Method != http.MethodGet {
		http.Error(w, "GET or POST required", 405)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]bool{"enabled": artifactMetadataDirect.Load()})
}
