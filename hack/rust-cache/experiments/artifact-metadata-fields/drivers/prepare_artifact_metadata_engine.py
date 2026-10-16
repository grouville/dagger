from pathlib import Path
import hashlib,json,shutil,subprocess

base=Path('/tmp/rust-cache-sipsma-review');root=base/'artifact-metadata-fields';previous=base/'parallel-fingerprint-engine';source=Path('/tmp/dagger-filesync-snapshot-seeds')
overlay=json.loads((root/'overlay.json').read_text())
for logical,item in json.loads((previous/'manifest.json').read_text()).items():assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest()==item['sha256'],logical
for name in ['engine.go.mod','engine.go.sum']:shutil.copyfile(previous/name,root/name)
schema=(root/'after.go').read_text();needle='\tartifactClass.Extend(dagql.FieldSpec{';assert schema.count(needle)==1
schema=schema.replace(needle,'\tinstallArtifactMetadataFieldsDiagnostic(srv)\n'+needle)
(root/'controlled.go').write_text(schema)
(root/'mode.go').write_text('''package schema
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
var artifactMetadataDirect atomic.Bool
func installArtifactMetadataFieldsDiagnostic(srv *dagql.Server) {
    object,ok:=srv.ObjectType("Artifact");if !ok {panic("missing Artifact")}
    class:=object.(dagql.Class[*core.Artifact])
    for _,name:=range []string{"description","uri"} {
        field,ok:=class.Field(name,"");if !ok {panic("missing artifact metadata field: "+name)}
        field.Spec.DoNotCache=""
        field.Spec.GetDynamicInput=func(_ context.Context,_ dagql.AnyResult,_ map[string]dagql.Input,_ call.View,req *dagql.CallRequest) error {req.DoNotCache=artifactMetadataDirect.Load();return nil}
    }
}
func ArtifactMetadataFieldsDiagnostic(w http.ResponseWriter,r *http.Request) {
    if r.Method==http.MethodPost {
        enabled,err:=strconv.ParseBool(r.URL.Query().Get("enabled"));if err!=nil {http.Error(w,err.Error(),400);return};artifactMetadataDirect.Store(enabled)
    } else if r.Method!=http.MethodGet {http.Error(w,"GET or POST required",405);return}
    w.Header().Set("Content-Type","application/json");_=json.NewEncoder(w).Encode(map[string]bool{"enabled":artifactMetadataDirect.Load()})
}
''')
debug=Path(overlay['Replace'][str(source/'cmd/engine/debug.go')]).read_text();needle='m := http.NewServeMux()';assert debug.count(needle)==1
debug=debug.replace(needle,needle+'\n    m.HandleFunc("/debug/artifact-metadata-fields",schema.ArtifactMetadataFieldsDiagnostic)');(root/'debug.go').write_text(debug)
overlay['Replace'][str(source/'core/schema/artifacts.go')]=str(root/'controlled.go')
overlay['Replace'][str(source/'core/schema/artifact_metadata_fields_mode.go')]=str(root/'mode.go')
overlay['Replace'][str(source/'cmd/engine/debug.go')]=str(root/'debug.go')
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
subprocess.run(['gofmt','-w',str(root/'controlled.go'),str(root/'mode.go'),str(root/'debug.go')],check=True)
print('Prepared reversible field policies; dimension-key lists remain cached')
