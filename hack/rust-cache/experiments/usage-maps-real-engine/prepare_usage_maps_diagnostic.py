from pathlib import Path
import hashlib,json,shutil
base=Path('/tmp/rust-cache-sipsma-review')
source=Path('/tmp/dagger-filesync-snapshot-seeds')
root=base/'usage-maps-real-engine'
root.mkdir(exist_ok=False)
original=json.loads((base/'fingerprint-buffer-engine-overlay.json').read_text())['Replace']
manifest=json.loads((base/'fingerprint-buffer-engine-overlay-manifest.json').read_text())
for path,item in manifest.items():
    assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest()==item['sha256'],path
replace=dict(original)
cache=Path(replace[str(source/'dagql/cache.go')]).read_text()
old='\t\tsizes := make(map[string]int64)\n\t\trecordTypes := make(map[string]string)'
new='\t\tvar sizes map[string]int64\n\t\tvar recordTypes map[string]string\n\t\tif !lazyUsageMapsDiagnostic.Load() {\n\t\t\tsizes = make(map[string]int64)\n\t\t\trecordTypes = make(map[string]string)\n\t\t}'
assert cache.count(old)==1
cache=cache.replace(old,new)
old='\t\tsizes[identity] = measurement.sizeBytes' # one extra indent inside actual loop
old='\t\t\tsizes[identity] = measurement.sizeBytes'
new='\t\t\tif sizes == nil {\n\t\t\t\tsizes = make(map[string]int64)\n\t\t\t}\n'+old
assert cache.count(old)==1
cache=cache.replace(old,new)
old='\t\t\tif measurement.recordType != "" {\n\t\t\t\trecordTypes[identity] = measurement.recordType'
new='\t\t\tif measurement.recordType != "" {\n\t\t\t\tif recordTypes == nil {\n\t\t\t\t\trecordTypes = make(map[string]string)\n\t\t\t\t}\n\t\t\t\trecordTypes[identity] = measurement.recordType'
assert cache.count(old)==1
cache=cache.replace(old,new)
(root/'cache.go').write_text(cache)
replace[str(source/'dagql/cache.go')]=str(root/'cache.go')
usage=(source/'dagql/cache_usage.go').read_text().replace('\t"errors"','\t"errors"\n\t"maps"')
usage=usage.replace('\n\t\texistingSizeByID: make(map[string]int64, len(res.cacheUsageSizeByIdentity)),','')
old='\tfor identity, size := range res.cacheUsageSizeByIdentity {\n\t\tinput.existingSizeByID[identity] = size\n\t}'
new='\tif lazyUsageMapsDiagnostic.Load() {\n\t\tif len(res.cacheUsageSizeByIdentity) != 0 {\n\t\t\tinput.existingSizeByID = maps.Clone(res.cacheUsageSizeByIdentity)\n\t\t}\n\t} else {\n\t\tinput.existingSizeByID = make(map[string]int64, len(res.cacheUsageSizeByIdentity))\n\t\tfor identity, size := range res.cacheUsageSizeByIdentity {\n\t\t\tinput.existingSizeByID[identity] = size\n\t\t}\n\t}'
assert usage.count(old)==1
usage=usage.replace(old,new)
(root/'cache_usage.go').write_text(usage)
replace[str(source/'dagql/cache_usage.go')]=str(root/'cache_usage.go')
(root/'mode.go').write_text('''package dagql

import (
    "context"
    "os"
    "runtime"
    "strconv"
    "sync/atomic"
    "time"
)

// Diagnostic-only switch. The upstream patch has no mode, endpoint or counters.
var lazyUsageMapsDiagnostic atomic.Bool
func init() {
    enabled, _ := strconv.ParseBool(os.Getenv("DAGGER_DIAG_LAZY_USAGE_MAPS"))
    lazyUsageMapsDiagnostic.Store(enabled)
}

// MeasureUsageDiagnostic prepares the existing prune state without planning
// or executing any eviction. The caller serializes it with actual GC.
func (c *Cache) MeasureUsageDiagnostic(ctx context.Context, enabled bool) (map[string]any, error) {
    previous := lazyUsageMapsDiagnostic.Swap(enabled)
    defer lazyUsageMapsDiagnostic.Store(previous)
    var before, after runtime.MemStats
    runtime.ReadMemStats(&before)
    start := time.Now()
    _, snapshot, complete, err := c.measurePruneState(ctx, 0)
    elapsed := time.Since(start)
    runtime.ReadMemStats(&after)
    return map[string]any{
        "enabled": enabled, "complete": complete, "rows": len(snapshot.results),
        "used_bytes": snapshot.usedBytes, "seconds": elapsed.Seconds(),
        "allocated_bytes": after.TotalAlloc-before.TotalAlloc,
        "allocations": after.Mallocs-before.Mallocs,
        "go_gc_cycles": after.NumGC-before.NumGC,
    }, err
}
''')
replace[str(source/'dagql/cache_usage_diagnostic.go')]=str(root/'mode.go')
(root/'server.go').write_text('''package server

import "context"

// Diagnostic only; do not change GC policy or delete cache entries.
func (srv *Server) MeasureCacheUsageDiagnostic(ctx context.Context, enabled bool) (map[string]any, error) {
    srv.gcmu.Lock()
    defer srv.gcmu.Unlock()
    return srv.engineCache.MeasureUsageDiagnostic(ctx, enabled)
}
''')
replace[str(source/'engine/server/cache_usage_diagnostic.go')]=str(root/'server.go')
debug=Path(replace[str(source/'cmd/engine/debug.go')]).read_text()
old='\tm := http.NewServeMux()'
new=old+'''
    m.HandleFunc("/debug/cache-usage-measurement", func(w http.ResponseWriter, r *http.Request) {
        if r.Method != http.MethodPost { http.Error(w, "POST required", 405); return }
        enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
        if err != nil { http.Error(w, err.Error(), 400); return }
        result, err := eng.MeasureCacheUsageDiagnostic(r.Context(), enabled)
        if err != nil { http.Error(w, err.Error(), 500); return }
        w.Header().Set("Content-Type", "application/json")
        _ = json.NewEncoder(w).Encode(result)
    })'''
assert debug.count(old)==1
(root/'debug.go').write_text(debug.replace(old,new))
replace[str(source/'cmd/engine/debug.go')]=str(root/'debug.go')
(root/'overlay.json').write_text(json.dumps({'Replace':replace},indent=2)+'\n')
shutil.copy('hack/rust-cache/experiments/fingerprint-buffer/engine-build-original.go.mod',root/'engine.go.mod')
shutil.copy(source/'go.sum',root/'engine.go.sum')
(root/'manifest.json').write_text(json.dumps({path:{'replacement':target,'sha256':hashlib.sha256(Path(target).read_bytes()).hexdigest()} for path,target in replace.items()},indent=2)+'\n')
print(root)
