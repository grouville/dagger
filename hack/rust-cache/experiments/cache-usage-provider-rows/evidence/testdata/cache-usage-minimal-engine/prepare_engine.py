from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).parent
work=Path('/tmp/dagger-cache-usage-sampler-only')
engine=Path('/tmp/dagger-filesync-snapshot-seeds')
overlay=json.loads(Path('/tmp/rust-cache-sipsma-review/dang-prepared-schema/engine-overlay.json').read_text())
def original(name):
    key=str(engine/name)
    return Path(overlay['Replace'].get(key,key)).read_text()
def between(source,start,end):
    return source[source.index(start):source.index(end,source.index(start))]
pure=(work/'dagql/cache_usage.go').read_text()
(root/'production-cache_usage.go').write_text(pure)
(root/'production-cache_usage_sparse_test.go').write_bytes((work/'dagql/cache_usage_sparse_test.go').read_bytes())
source=original('dagql/cache_usage.go')
source=source.replace('cache        *Cache\n','cache        *Cache\n\tsparse       bool\n',1)
source=source.replace('cache: c, op: op,','cache: c, op: op, sparse: usageSamplingFor(ctx),',1)
source=source.replace('func (snapshot *cacheUsageSnapshot) capturePendingLocked(', 'func (snapshot *cacheUsageSnapshot) legacyCapturePendingLocked(',1)
source=source.replace('func (snapshot *cacheUsageSnapshot) finalizeLocked(', 'func (snapshot *cacheUsageSnapshot) legacyFinalizeLocked(',1)
source=source.replace('cacheUsageInputLocked(', 'legacyCacheUsageInputLocked(')
helper=between(pure,'func cacheUsageInputLocked(', '// Identity-free values')
oldmap=between(source,'\tif lazyUsageMapsDiagnostic.Load() {','\treturn input\n')
newmap=between(helper,'\tfor identity, size := range res.cacheUsageSizeByIdentity {','\treturn input\n')
helper=helper.replace('\n\t\texistingSizeByID: make(map[string]int64, len(res.cacheUsageSizeByIdentity)),','',1)
assert helper.count(newmap)==1
helper=helper.replace(newmap,oldmap,1)
capture=between(pure,'func (snapshot *cacheUsageSnapshot) capturePendingLocked(', 'func (input cacheUsageMeasurementInput) validLocked(')
capture=capture.replace('capturePendingLocked(ctx context.Context) []cacheUsageMeasurementInput {','capturePendingLocked(ctx context.Context) []cacheUsageMeasurementInput {\n\tif !snapshot.sparse { return snapshot.legacyCapturePendingLocked(ctx) }',1)
capture=capture.replace('finalizeLocked() (map[sharedResultID][]string, error) {','finalizeLocked() (map[sharedResultID][]string, error) {\n\tif !snapshot.sparse { return snapshot.legacyFinalizeLocked() }',1)
anchor='func legacyCacheUsageInputLocked('
source=source.replace(anchor,helper+capture+anchor,1)
(root/'controlled-cache_usage.go').write_text(source)
source=original('dagql/cache_prune.go')
anchor='func (c *Cache) Prune(ctx context.Context, policies []CachePrunePolicy) (CachePruneReport, error) {'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n\tctx = usageSamplingContext(ctx)',1)
(root/'controlled-cache_prune.go').write_text(source)
(root/'mode.go').write_text('''package dagql
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
 if enabled, ok := ctx.Value(usageSamplingKey{}).(bool); ok { return enabled }
 return usageSamplingEnabled.Load()
}
func usageSamplingContext(ctx context.Context) context.Context {
 return context.WithValue(ctx, usageSamplingKey{}, usageSamplingFor(ctx))
}
func UsageSamplingDiagnostic(w http.ResponseWriter, r *http.Request) {
 if r.Method==http.MethodPost {
  enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
  if err!=nil { http.Error(w,err.Error(),http.StatusBadRequest);return }
  usageSamplingEnabled.Store(enabled)
 } else if r.Method!=http.MethodGet { http.Error(w,"GET or POST required",http.StatusMethodNotAllowed);return }
 w.Header().Set("Content-Type","application/json")
 _=json.NewEncoder(w).Encode(map[string]any{"enabled":usageSamplingEnabled.Load()})
}
''')
(root/'mode_test.go').write_text('''package dagql
import "os"
func init() { usageSamplingEnabled.Store(os.Getenv("DAGGER_USAGE_SAMPLING_TEST_MODE")=="on") }
''')
source=original('cmd/engine/debug.go')
anchor='m.HandleFunc("/debug/prepared-schema", dangv2.PreparedSchemaDiagnostic)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n\tm.HandleFunc("/debug/usage-sampling", dagql.UsageSamplingDiagnostic)',1)
(root/'debug.go').write_text(source)
for name,target in [('cache_usage.go','controlled-cache_usage.go'),('cache_prune.go','controlled-cache_prune.go'),('cache_usage_sampling_mode.go','mode.go'),('cache_usage_sampling_mode_test.go','mode_test.go'),('cache_usage_sparse_test.go','production-cache_usage_sparse_test.go')]:
    overlay['Replace'][str(engine/'dagql'/name)]=str(root/target)
overlay['Replace'][str(engine/'cmd/engine/debug.go')]=str(root/'debug.go')
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
subprocess.run(['/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt','-w',*[str(root/name) for name in ['controlled-cache_usage.go','controlled-cache_prune.go','mode.go','mode_test.go','debug.go']]],check=True)
(root/'source-hashes.json').write_text(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['production-cache_usage.go','production-cache_usage_sparse_test.go','controlled-cache_usage.go','controlled-cache_prune.go','mode.go','mode_test.go','debug.go']},indent=2)+'\n')
print('Prepared sampler-only controlled sources. No policy preflight change; legacy disabled path retained.')
