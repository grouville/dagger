from pathlib import Path
import hashlib
import json
import subprocess

root=Path(__file__).parent
base=root.parent
source=Path('/tmp/dagger-filesync-snapshot-seeds')
upstream=Path('/tmp/dagger-collection-expansion-limit-upstream')
old=base/'interface-field-snapshots'
overlay=json.loads((old/'engine-overlay.json').read_text())
manifest=json.loads((old/'manifest.json').read_text())
for entry in manifest.values():
    assert hashlib.sha256(Path(entry['replacement']).read_bytes()).hexdigest()==entry['sha256'],entry['replacement']

key=str(source/'core/artifact_collection.go')
original=Path(overlay['Replace'].get(key,key)).read_text()
needle='children := make([][]*ModTreeNode, len(parents))\n\tgroup, ctx := errgroup.WithContext(ctx)'
assert original.count(needle)==1
static=original.replace(needle,needle+'\n\tgroup.SetLimit(32)')
(root/'static-artifact-collection.go').write_text(static)
controlled=original.replace(needle,needle+'''
    if limit := int(collectionExpansionLimit.Load()); limit > 0 { group.SetLimit(limit) }
''')
needle='''			keys, err := collectionKeys(ctx, &Artifact{Node: parent, Workspace: template.Workspace, ContextWorkspace: template.ContextWorkspace})'''
assert controlled.count(needle)==1
controlled=controlled.replace(needle,'''
            active := collectionExpansionActive.Add(1)
            collectionExpansionStarted.Add(1)
            for peak := collectionExpansionPeak.Load(); active > peak; peak = collectionExpansionPeak.Load() {
                if collectionExpansionPeak.CompareAndSwap(peak,active) {break}
            }
            defer collectionExpansionActive.Add(-1)
'''+needle)
(root/'controlled-artifact-collection.go').write_text(controlled)
(root/'mode.go').write_text('''package core

import (
    "encoding/json"
    "net/http"
    "strconv"
    "sync/atomic"
)

var collectionExpansionLimit atomic.Int64
var collectionExpansionActive atomic.Int64
var collectionExpansionPeak atomic.Int64
var collectionExpansionStarted atomic.Int64

func CollectionExpansionLimitDiagnostic(w http.ResponseWriter,r *http.Request) {
    if r.Method == http.MethodPost {
        limit,err := strconv.ParseInt(r.URL.Query().Get("limit"),10,64)
        if err != nil || limit < 0 || limit > 4096 {http.Error(w,"limit must be between 0 and 4096",400);return}
        if collectionExpansionActive.Load() != 0 {http.Error(w,"collection expansion is active",409);return}
        collectionExpansionLimit.Store(limit)
        collectionExpansionPeak.Store(0)
        collectionExpansionStarted.Store(0)
    } else if r.Method != http.MethodGet {http.Error(w,"GET or POST required",405);return}
    w.Header().Set("Content-Type","application/json")
    _=json.NewEncoder(w).Encode(map[string]int64{
        "limit":collectionExpansionLimit.Load(),"active":collectionExpansionActive.Load(),
        "peak":collectionExpansionPeak.Load(),"started":collectionExpansionStarted.Load(),
    })
}
''')
test_overlay=json.loads(json.dumps(overlay))
test_overlay['Replace'][key]=str(root/'static-artifact-collection.go')
test_overlay['Replace'][str(source/'core/artifact_collection_test.go')]=str(upstream/'core/artifact_collection_test.go')
(root/'test-overlay.json').write_text(json.dumps(test_overlay,indent=2)+'\n')
overlay['Replace'][key]=str(root/'controlled-artifact-collection.go')
overlay['Replace'][str(source/'core/artifact_collection_expansion_limit_diagnostic.go')]=str(root/'mode.go')
debug=Path(overlay['Replace'][str(source/'cmd/engine/debug.go')]).read_text()
if '"github.com/dagger/dagger/core"' not in debug:
    debug=debug.replace('"github.com/dagger/dagger/dagql"','"github.com/dagger/dagger/core"\n"github.com/dagger/dagger/dagql"',1)
needle='m := http.NewServeMux()';assert debug.count(needle)==1
debug=debug.replace(needle,needle+'\n m.HandleFunc("/debug/collection-expansion-limit",core.CollectionExpansionLimitDiagnostic)')
(root/'debug.go').write_text(debug)
overlay['Replace'][str(source/'cmd/engine/debug.go')]=str(root/'debug.go')
(root/'engine-overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
for name in ['engine.go.mod','engine.go.sum']:(root/name).write_bytes((old/name).read_bytes())
subprocess.run(['/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt','-w',
    *[str(root/name) for name in ['static-artifact-collection.go','controlled-artifact-collection.go','mode.go','debug.go']]],check=True)
manifest={k:dict(replacement=v,sha256=hashlib.sha256(Path(v).read_bytes()).hexdigest()) for k,v in overlay['Replace'].items()}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(root/'baseline-correspondence.json').write_text(json.dumps(dict(
    original_sha256=hashlib.sha256(original.encode()).hexdigest(),
    note='Runtime limit 0 preserves the previous expansion body, with only shared active/peak counters added to both arms. Static test overlay uses the proposed limit 32.'),indent=2)+'\n')
print('Prepared controlled expansion limit; default 0 preserves unbounded behavior.')
