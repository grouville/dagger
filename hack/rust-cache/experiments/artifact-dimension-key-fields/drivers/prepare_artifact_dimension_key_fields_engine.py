from pathlib import Path
import hashlib
import json
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
previous = base / 'spill-batch-buffers-engine'
root = base / 'artifact-dimension-key-fields-engine'
source = Path('/tmp/dagger-filesync-snapshot-seeds')
root.mkdir(exist_ok=False)
overlay = json.loads((previous / 'overlay.json').read_text())
for logical, item in json.loads((previous / 'manifest.json').read_text()).items():
    assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest() == item['sha256'], logical
for name in ('engine.go.mod', 'engine.go.sum'):
    shutil.copyfile(previous / name, root / name)

production = Path(overlay['Replace'].get(str(source / 'core/artifacts.go'), str(source / 'core/artifacts.go'))).read_text()
for description in ('The dimension identifier, fixed across the workspace schema.', "The dimension item's key."):
    needle = f'doc:"{description}"`'
    assert production.count(needle) == 1
    production = production.replace(needle, f'doc:"{description}" doNotCache:"simple field selection"`')
(root / 'artifacts.go').write_text(production)

schema = Path(overlay['Replace'].get(str(source / 'core/schema/artifacts.go'), str(source / 'core/schema/artifacts.go'))).read_text()
needle = '\tdagql.Fields[*core.ArtifactDimensionKey]{}.Install(srv)'
assert schema.count(needle) == 1
schema = schema.replace(needle, needle + '\n\tinstallDimensionKeyFieldsDiagnostic(srv)')
(root / 'schema.go').write_text(schema)
(root / 'mode.go').write_text('''package schema

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
        if !ok { panic("missing dimension-key field: " + name) }
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
        if err != nil { http.Error(w, err.Error(), http.StatusBadRequest); return }
        dimensionKeyFieldsDirect.Store(enabled)
    } else if r.Method != http.MethodGet {
        http.Error(w, "GET or POST required", http.StatusMethodNotAllowed); return
    }
    w.Header().Set("Content-Type", "application/json")
    _ = json.NewEncoder(w).Encode(map[string]bool{"enabled": dimensionKeyFieldsDirect.Load()})
}
''')

debug = Path(overlay['Replace'][str(source / 'cmd/engine/debug.go')]).read_text()
needle = '\t"github.com/dagger/dagger/dagql"'
assert debug.count(needle) == 1
debug = debug.replace(needle, '\t"github.com/dagger/dagger/core/schema"\n' + needle)
needle = '\tm := http.NewServeMux()'
assert debug.count(needle) == 1
debug = debug.replace(needle, needle + '\n\tm.HandleFunc("/debug/dimension-key-fields", schema.DimensionKeyFieldsDiagnostic)')
(root / 'debug.go').write_text(debug)

updates = {
    str(source / 'core/artifacts.go'): str(root / 'artifacts.go'),
    str(source / 'core/schema/artifacts.go'): str(root / 'schema.go'),
    str(source / 'core/schema/artifact_dimension_key_fields_mode.go'): str(root / 'mode.go'),
    str(source / 'core/schema/artifact_dimension_key_fields_test.go'): str(base / 'artifact-dimension-key-fields_test.go'),
    str(source / 'cmd/engine/debug.go'): str(root / 'debug.go'),
}
overlay['Replace'].update(updates)
subprocess.run(['gofmt', '-w', *[str(root / name) for name in ('artifacts.go', 'schema.go', 'mode.go', 'debug.go')], str(base / 'artifact-dimension-key-fields_test.go')], check=True)
(root / 'overlay.json').write_text(json.dumps(overlay, indent=2) + '\n')
manifest = {logical: dict(replacement=path, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()) for logical, path in overlay['Replace'].items()}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
metadata = dict(
    previous_engine_sha256=json.loads((previous / 'identity.json').read_text())['engine_sha256'],
    base_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
    feature='Read the two immutable ArtifactDimensionKey string fields directly, matching TypeDef getters.',
    production_change='Two doNotCache struct tags in core/artifacts.go; the atomic mode and dynamic policy callback are diagnostic only.',
    default_enabled=False,
    diagnostic_route='/debug/dimension-key-fields',
    unchanged_dependency_overlays=True,
    build_command=['go', 'build', '-buildvcs=false', '-modfile', str(root / 'engine.go.mod'), '-overlay', str(root / 'overlay.json'), '-o', str(root / 'dagger-engine'), './cmd/engine'],
)
(root / 'provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
print('Prepared diagnostic engine; prior overlay hashes verified. Production delta: two struct tags.')
