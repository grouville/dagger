from pathlib import Path
import json
root=Path(__file__).parent
work=Path('/tmp/dagger-cache-usage-provider-rows')
engine=Path('/tmp/dagger-filesync-snapshot-seeds')
overlay=json.loads(Path('/tmp/rust-cache-sipsma-review/dang-prepared-schema/engine-overlay.json').read_text())
def original(name):
 key=str(engine/name)
 return Path(overlay['Replace'].get(key,key)).read_text()
def between(source,start,end):return source[source.index(start):source.index(end,source.index(start))]

source=original('dagql/cache_usage.go')
pure=(work/'dagql/cache_usage.go').read_text()
helper=between(pure,'// Rows without usage identities','func (snapshot *cacheUsageSnapshot) capturePendingLocked')
anchor='func (snapshot *cacheUsageSnapshot) capturePendingLocked'
source=source.replace(anchor,helper+anchor,1)
source=source.replace('cache        *Cache\n','cache        *Cache\n\tsparse       bool\n',1)
source=source.replace('cache: c, op: op,','cache: c, op: op, sparse: usagePrunePreflightFor(ctx),',1)
anchor='for id, res := range snapshot.cache.resultsByID {\n'
assert source.count(anchor)==2
source=source.replace(anchor,anchor+'\t\tif snapshot.sparse && cacheUsageIsEmptyLocked(res) {\n\t\t\tcontinue\n\t\t}\n')
anchor='identities := make(map[sharedResultID][]string, len(snapshot.cache.resultsByID))'
assert source.count(anchor)==1
source=source.replace(anchor,'capacity := len(snapshot.cache.resultsByID)\n\tif snapshot.sparse {\n\t\tcapacity = len(snapshot.inputs)\n\t}\n\tidentities := make(map[sharedResultID][]string, capacity)',1)
(root/'controlled-cache_usage.go').write_text(source)

source=original('dagql/cache.go');pure=(work/'dagql/cache.go').read_text()
start='func (c *Cache) measureAllResultSizes('
end='func buildCacheUsageMeasurements('
old=between(source,start,end);new=between(pure,start,end)
source=source.replace(old,new,1)
start='func (c *Cache) publishUsageMeasurementsLocked('
end='// Core cache lookup/insert flow'
old=between(source,start,end);new=old
signature='identities map[sharedResultID][]string) {'
assert new.count(signature)==1
new=new.replace(signature,'identities map[sharedResultID][]string) int64 {',1)
anchor='\tfor id, res := range c.resultsByID {'
assert new.count(anchor)==1
new=new.replace(anchor,'\tvar usedBytes int64\n'+anchor,1)
anchor='\t\t\tsizes[identity] = measurement.sizeBytes\n'
assert new.count(anchor)==1
new=new.replace(anchor,anchor+'\t\t\tif measurement.sizeBytes > 0 {\n\t\t\t\tusedBytes += measurement.sizeBytes\n\t\t\t}\n',1)
assert new.endswith('}\n\n')
new=new[:-3]+'\treturn usedBytes\n}\n\n'
source=source.replace(old,new,1)
(root/'controlled-cache.go').write_text(source)

source=original('dagql/cache_prune.go');pure=(work/'dagql/cache_prune.go').read_text()
start='func (c *Cache) measurePruneState('
end='func (c *Cache) Prune('
old=between(source,start,end);new=between(pure,start,end)
new=new.replace('if target, _ := pruneTargetBytes(policy, usedBytes); target <= 0 {','usagePruneMeasuredBytes.Store(usedBytes)\n\t\tif target, _ := pruneTargetBytes(policy, usedBytes); usagePrunePreflightFor(ctx) && target <= 0 {\n\t\t\tusagePruneShortcuts.Add(1)',1)
new=new.replace('\tsnapshot, err := c.snapshotPruneStateCancelable(', '\tusagePruneSnapshots.Add(1)\n\tsnapshot, err := c.snapshotPruneStateCancelable(',1)
source=source.replace(old,new,1)
assert source.count('c.measurePruneState(ctx, policyIdx)')==2
source=source.replace('c.measurePruneState(ctx, policyIdx)','c.measurePruneState(ctx, policyIdx, policy)')
source=source.replace('func (c *Cache) Prune(ctx context.Context, policies []CachePrunePolicy) (CachePruneReport, error) {','func (c *Cache) Prune(ctx context.Context, policies []CachePrunePolicy) (CachePruneReport, error) {\n\tctx = usagePrunePreflightContext(ctx)',1)
(root/'controlled-cache_prune.go').write_text(source)

source=(work/'dagql/cache_usage_chain_test.go').read_text()
source=source.replace('if identityCalls != 1 {','wantNoTarget := 1\n\tif !usagePrunePreflightEnabled.Load() { wantNoTarget = 2 }\n\tif identityCalls != wantNoTarget {',1)
source=source.replace('if identityCalls != 3 {','wantAfterRemoval := 3\n\tif !usagePrunePreflightEnabled.Load() { wantAfterRemoval = 4 }\n\tif identityCalls != wantAfterRemoval {',1)
(root/'controlled-cache_usage_chain_test.go').write_text(source)
(root/'mode.go').write_text('''package dagql
import (
 "context"
 "encoding/json"
 "net/http"
 "strconv"
 "sync/atomic"
)
var usagePrunePreflightEnabled atomic.Bool
var usagePruneShortcuts, usagePruneSnapshots atomic.Uint64
var usagePruneMeasuredBytes atomic.Int64
type usagePrunePreflightKey struct{}
func usagePrunePreflightFor(ctx context.Context) bool {
 if enabled, ok := ctx.Value(usagePrunePreflightKey{}).(bool); ok { return enabled }
 return usagePrunePreflightEnabled.Load()
}
func usagePrunePreflightContext(ctx context.Context) context.Context {
 return context.WithValue(ctx, usagePrunePreflightKey{}, usagePrunePreflightFor(ctx))
}
func UsagePrunePreflightDiagnostic(w http.ResponseWriter, r *http.Request) {
 if r.Method==http.MethodPost {
  enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
  if err!=nil { http.Error(w,err.Error(),http.StatusBadRequest);return }
  usagePrunePreflightEnabled.Store(enabled)
 } else if r.Method!=http.MethodGet { http.Error(w,"GET or POST required",http.StatusMethodNotAllowed);return }
 w.Header().Set("Content-Type","application/json")
 _=json.NewEncoder(w).Encode(map[string]any{"enabled":usagePrunePreflightEnabled.Load(),"no_target_passes":usagePruneShortcuts.Load(),"full_snapshots":usagePruneSnapshots.Load(),"last_nonblob_measured_bytes":usagePruneMeasuredBytes.Load()})
}
''')
(root/'mode_test.go').write_text('''package dagql
import "os"
func init() { usagePrunePreflightEnabled.Store(os.Getenv("DAGGER_USAGE_PREFLIGHT_TEST_MODE")=="on") }
''')
source=original('cmd/engine/debug.go')
anchor='m.HandleFunc("/debug/prepared-schema", dangv2.PreparedSchemaDiagnostic)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n\tm.HandleFunc("/debug/prune-usage-preflight", dagql.UsagePrunePreflightDiagnostic)',1)
(root/'debug.go').write_text(source)
for name,target in [('cache.go','controlled-cache.go'),('cache_usage.go','controlled-cache_usage.go'),('cache_prune.go','controlled-cache_prune.go'),('cache_usage_chain_test.go','controlled-cache_usage_chain_test.go'),('cache_usage_preflight_mode.go','mode.go'),('cache_usage_preflight_mode_test.go','mode_test.go')]:
 overlay['Replace'][str(engine/'dagql'/name)]=str(root/target)
overlay['Replace'][str(engine/'dagql/cache_usage_sparse_test.go')]=str(work/'dagql/cache_usage_sparse_test.go')
overlay['Replace'][str(engine/'cmd/engine/debug.go')]=str(root/'debug.go')
legacy_mode=Path('/tmp/rust-cache-sipsma-review/usage-maps-real-engine/mode.go')
legacy_source=legacy_mode.read_text().replace('c.measurePruneState(ctx, 0)', 'c.measurePruneState(ctx, 0, CachePrunePolicy{All: true})')
(root/'usage-measurement-mode.go').write_text(legacy_source)
for key,value in list(overlay['Replace'].items()):
 if value==str(legacy_mode): overlay['Replace'][key]=str(root/'usage-measurement-mode.go')
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
print('Prepared controlled engine sources with one captured mode per prune and per usage snapshot.')
