from pathlib import Path
import hashlib,json,shutil,subprocess

base=Path('/tmp/rust-cache-sipsma-review')
previous=base/'containerd-root-dedup-single-lookup-engine'
root=base/'spill-batch-buffers-engine'
root.mkdir(exist_ok=False)
source=Path('/tmp/dagger-filesync-snapshot-seeds')
candidate=Path('/tmp/dagger-telemetry-spill-batch-buffers')
old=json.loads((previous/'overlay.json').read_text())
manifest=json.loads((previous/'manifest.json').read_text())
for logical,item in manifest.items():
    assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest()==item['sha256'],logical
shutil.copyfile(previous/'engine.go.mod',root/'engine.go.mod')
shutil.copyfile(previous/'engine.go.sum',root/'engine.go.sum')
s=(candidate/'engine/clientdb/store_spill.go').read_text()
start=s.index('func (s *spillFile[Row]) readSince(')
end=s.index('\nfunc (s *spillFile[Row]) readID(',start)
body=s[start:end]
body=body.replace('\tdefer scanner.release()','\treuse := spillBatchBuffers.Load()\n\tif reuse {\n\t\tdefer scanner.release()\n\t}')
body=body.replace('\t\tpayload, err = scanner.nextInto(payload[:0])','\t\tif reuse {\n\t\t\tpayload, err = scanner.nextInto(payload[:0])\n\t\t} else {\n\t\t\tpayload, err = scanner.next()\n\t\t}')
assert 'spillBatchBuffers.Load()' in body
(root/'store_spill.go').write_text(s[:start]+body+s[end:])
(root/'mode.go').write_text('''package clientdb

import (
    "encoding/json"
    "net/http"
    "strconv"
    "sync/atomic"
)

var spillBatchBuffers atomic.Bool

func SpillBatchBuffersDiagnostic(w http.ResponseWriter, r *http.Request) {
    if r.Method == http.MethodPost {
        enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
        if err != nil { http.Error(w, err.Error(), http.StatusBadRequest); return }
        spillBatchBuffers.Store(enabled)
    } else if r.Method != http.MethodGet {
        http.Error(w, "GET or POST required", http.StatusMethodNotAllowed); return
    }
    w.Header().Set("Content-Type", "application/json")
    _ = json.NewEncoder(w).Encode(map[string]bool{"enabled": spillBatchBuffers.Load()})
}
''')
(root/'mode_test.go').write_text('''package clientdb
import "testing"
func TestSpillBatchBufferDiagnosticModes(t *testing.T) {
    for _, enabled := range []bool{false, true} {
        spillBatchBuffers.Store(enabled)
        TestSpillFileReadSinceOwnsRows(t)
    }
    spillBatchBuffers.Store(false)
}
''')
debug=Path(old['Replace'][str(source/'cmd/engine/debug.go')]).read_text()
needle='\tm.HandleFunc("/debug/batch-metadata", clientdb.BatchMetadataDiagnostic)'
assert debug.count(needle)==1
debug=debug.replace(needle,'\tm.HandleFunc("/debug/spill-batch-buffers", clientdb.SpillBatchBuffersDiagnostic)\n'+needle)
(root/'debug.go').write_text(debug)
updates={
 str(source/'engine/clientdb/store_spill.go'):str(root/'store_spill.go'),
 str(source/'engine/clientdb/spill_batch_buffers_mode.go'):str(root/'mode.go'),
 str(source/'engine/clientdb/spill_batch_buffers_mode_test.go'):str(root/'mode_test.go'),
 str(source/'engine/clientdb/store_spill_test.go'):str(candidate/'engine/clientdb/store_spill_test.go'),
 str(source/'cmd/engine/debug.go'):str(root/'debug.go'),
}
old['Replace'].update(updates)
(root/'overlay.json').write_text(json.dumps(old,indent=2)+'\n')
subprocess.run(['gofmt','-w',*[str(root/name) for name in ['store_spill.go','mode.go','mode_test.go','debug.go']]],check=True)
manifest={logical:dict(replacement=path,sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()) for logical,path in old['Replace'].items()}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
meta=dict(previous_engine_sha256='e174ad0a118c3312cebae1333d4dbaf1f2a1d3f56656a337629830bbe18092e8',
          base_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
          feature='Reuse telemetry spill payload buffer and release the reader for batch reads.',
          default_enabled=False,diagnostic_route='/debug/spill-batch-buffers',
          production_source=str(candidate/'engine/clientdb/store_spill.go'),
          production_source_sha256=hashlib.sha256((candidate/'engine/clientdb/store_spill.go').read_bytes()).hexdigest(),
          unchanged_dependency_overlays=True,protobuf_small_sort_installed=False,
          build_command=['go','build','-buildvcs=false','-modfile',str(root/'engine.go.mod'),'-overlay',str(root/'overlay.json'),'-o',str(root/'dagger-engine'),'./cmd/engine'])
(root/'provenance.json').write_text(json.dumps(meta,indent=2)+'\n')
print('Prepared diagnostic engine; all previous overlay hashes match',flush=True)
