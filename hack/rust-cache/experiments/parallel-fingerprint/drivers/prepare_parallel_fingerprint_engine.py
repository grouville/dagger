from pathlib import Path
import hashlib
import json
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
previous = base / 'artifact-dimension-key-fields-engine'
root = base / 'parallel-fingerprint-engine'
root.mkdir(exist_ok=False)
source = Path('/tmp/dagger-filesync-snapshot-seeds')
experiment = base / 'parallel-fingerprint'
overlay = json.loads((previous / 'overlay.json').read_text())
for logical, item in json.loads((previous / 'manifest.json').read_text()).items():
    assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest() == item['sha256'], logical
for name in ['engine.go.mod', 'engine.go.sum']:
    shutil.copyfile(previous / name, root / name)

(root / 'parallel.go').write_text((experiment / 'after.go').read_text().replace('func TreeFingerprint(', 'func treeFingerprintParallel('))
(root / 'serial.go').write_text((experiment / 'before.go').read_text().replace('func TreeFingerprint(', 'func treeFingerprintSerial('))
(root / 'mode.go').write_text('''package contenthash

import (
    "context"
    "encoding/json"
    "net/http"
    "strconv"
    "sync/atomic"
    digest "github.com/opencontainers/go-digest"
)

var parallelFingerprint atomic.Bool

func TreeFingerprint(ctx context.Context, root string, ignoreContents, reject []string) (digest.Digest, error) {
    if parallelFingerprint.Load() { return treeFingerprintParallel(ctx, root, ignoreContents, reject) }
    return treeFingerprintSerial(ctx, root, ignoreContents, reject)
}

func ParallelFingerprintDiagnostic(w http.ResponseWriter, r *http.Request) {
    if r.Method == http.MethodPost {
        enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
        if err != nil { http.Error(w, err.Error(), http.StatusBadRequest); return }
        parallelFingerprint.Store(enabled)
    } else if r.Method != http.MethodGet {
        http.Error(w, "GET or POST required", http.StatusMethodNotAllowed); return
    }
    w.Header().Set("Content-Type", "application/json")
    _ = json.NewEncoder(w).Encode(map[string]bool{"enabled": parallelFingerprint.Load()})
}
''')
(root / 'mode_test.go').write_text('''package contenthash
import "testing"
func TestParallelFingerprintDiagnosticModes(t *testing.T) {
    defer parallelFingerprint.Store(false)
    for _, enabled := range []bool{false, true} {
        parallelFingerprint.Store(enabled)
        TestTreeFingerprintParallelCompatibility(t)
        TestTreeFingerprintDiscoveryInputs(t)
        TestTreeFingerprintUnsupportedInputs(t)
        TestTreeFingerprintCanonicalOrder(t)
    }
}
''')
debug = Path(overlay['Replace'][str(source / 'cmd/engine/debug.go')]).read_text()
needle = '\t"github.com/dagger/dagger/engine/clientdb"'; assert debug.count(needle) == 1
debug = debug.replace(needle, '\t"github.com/dagger/dagger/engine/contenthash"\n' + needle)
needle = '\tm := http.NewServeMux()'; assert debug.count(needle) == 1
debug = debug.replace(needle, needle + '\n\tm.HandleFunc("/debug/parallel-fingerprint", contenthash.ParallelFingerprintDiagnostic)')
(root / 'debug.go').write_text(debug)

overlay['Replace'].update({
    str(source / 'engine/contenthash/fingerprint.go'): str(root / 'parallel.go'),
    str(source / 'engine/contenthash/fingerprint_serial.go'): str(root / 'serial.go'),
    str(source / 'engine/contenthash/fingerprint_mode.go'): str(root / 'mode.go'),
    str(source / 'engine/contenthash/fingerprint_mode_test.go'): str(root / 'mode_test.go'),
    str(source / 'engine/contenthash/fingerprint_reference_test.go'): str(experiment / 'reference_test.go'),
    str(source / 'engine/contenthash/fingerprint_parallel_linux_test.go'): str(experiment / 'parallel_test.go'),
    str(source / 'cmd/engine/debug.go'): str(root / 'debug.go'),
})
subprocess.run(['gofmt', '-w', *[str(root / name) for name in ['parallel.go', 'serial.go', 'mode.go', 'mode_test.go', 'debug.go']], str(experiment / 'parallel_test.go')], check=True)
(root / 'overlay.json').write_text(json.dumps(overlay, indent=2) + '\n')
manifest = {logical: dict(replacement=path, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()) for logical, path in overlay['Replace'].items()}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
metadata = dict(
    previous_engine_sha256=json.loads((previous / 'identity.json').read_text())['engine_sha256'],
    base_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip(),
    feature='Fingerprint immutable entries in bounded 128-entry batches with up to eight workers; preserve serial digest bytes.',
    default_enabled=False, diagnostic_route='/debug/parallel-fingerprint',
    worker_and_module_unchanged=True, unchanged_dependency_overlays=True,
    build_command=['go', 'build', '-buildvcs=false', '-modfile', str(root / 'engine.go.mod'), '-overlay', str(root / 'overlay.json'), '-o', str(root / 'dagger-engine'), './cmd/engine'],
)
(root / 'provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
print('Prepared engine with serial/parallel switch; all previous source hashes verified.')
