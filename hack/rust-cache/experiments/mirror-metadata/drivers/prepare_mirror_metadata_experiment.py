from pathlib import Path
import hashlib
import json
import shutil
import subprocess

base=Path('/tmp/rust-cache-sipsma-review')
source=Path('/tmp/dagger-filesync-snapshot-seeds')
root=base/'mirror-metadata'
root.mkdir(exist_ok=False)

def replace(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)

fs=(source/'internal/fsutil/fs.go').read_text()
fs=replace(fs,'func NewFS(root string) (FS, error) {','''func NewFS(root string) (FS, error) {
    return NewFSWithOptions(root, FSOptions{})
}

// FSOptions controls which metadata a filesystem walk reads.
type FSOptions struct {
    // SkipXattrs omits extended attributes from returned file stats.
    SkipXattrs bool
}

// NewFSWithOptions creates a filesystem with explicitly selected metadata.
func NewFSWithOptions(root string, options FSOptions) (FS, error) {''')
fs=replace(fs,'root: root,','root: root,\n        skipXattrs: options.SkipXattrs,')
fs=replace(fs,'type fs struct {\n\troot string\n}','type fs struct {\n\troot string\n    skipXattrs bool\n}')
fs=replace(fs,'seenFiles: seenFiles,','seenFiles: seenFiles,\n                skipXattrs: fs.skipXattrs,')
fs=replace(fs,'seenFiles map[uint64]string\n}','seenFiles map[uint64]string\n    skipXattrs bool\n}')
fs=replace(fs,'mkstat(s.origpath, s.path, fi, s.seenFiles)','mkstat(s.origpath, s.path, fi, s.seenFiles, s.skipXattrs)')
(root/'fs.go').write_text(fs)
stat=(source/'internal/fsutil/stat.go').read_text()
stat=replace(stat,'inodemap map[uint64]string) (*types.Stat, error)','inodemap map[uint64]string, skipXattrs bool) (*types.Stat, error)')
stat=replace(stat,'if err := loadXattr(path, stat); err != nil {\n\t\treturn nil, err\n\t}','if !skipXattrs {\n        if err := loadXattr(path, stat); err != nil {\n            return nil, err\n        }\n    }')
stat=replace(stat,'mkstat(path, filepath.Base(path), fi, nil)','mkstat(path, filepath.Base(path), fi, nil, false)')
(root/'stat.go').write_text(stat)
local=(source/'engine/filesync/localfs.go').read_text()
local=replace(local,'fsutil.NewFS(filepath.Join(sharedState.rootPath, subdir))','fsutil.NewFSWithOptions(filepath.Join(sharedState.rootPath, subdir), fsutil.FSOptions{SkipXattrs: mirrorMetadataSkipXattrs.Load()})')
(root/'localfs.go').write_text(local)
(root/'mode.go').write_text('''package filesync
import (
    "encoding/json"
    "net/http"
    "strconv"
    "sync/atomic"
)
var mirrorMetadataSkipXattrs atomic.Bool
func MirrorMetadataDiagnostic(w http.ResponseWriter,r *http.Request) {
    if r.Method==http.MethodPost {
        enabled,err:=strconv.ParseBool(r.URL.Query().Get("enabled"))
        if err!=nil {http.Error(w,err.Error(),http.StatusBadRequest);return}
        mirrorMetadataSkipXattrs.Store(enabled)
    } else if r.Method!=http.MethodGet {http.Error(w,"GET or POST required",http.StatusMethodNotAllowed);return}
    w.Header().Set("Content-Type","application/json")
    _=json.NewEncoder(w).Encode(map[string]bool{"enabled":mirrorMetadataSkipXattrs.Load()})
}
''')

previous=base/'parallel-fingerprint-engine'
overlay=json.loads((previous/'overlay.json').read_text())
for logical,item in json.loads((previous/'manifest.json').read_text()).items():
    assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest()==item['sha256'],logical
for name in ['engine.go.mod','engine.go.sum']:shutil.copyfile(previous/name,root/name)
debug=Path(overlay['Replace'][str(source/'cmd/engine/debug.go')]).read_text()
debug=replace(debug,'"github.com/dagger/dagger/engine/contenthash"','"github.com/dagger/dagger/engine/contenthash"\n    "github.com/dagger/dagger/engine/filesync"')
debug=replace(debug,'m := http.NewServeMux()','m := http.NewServeMux()\n    m.HandleFunc("/debug/mirror-metadata",filesync.MirrorMetadataDiagnostic)')
(root/'debug.go').write_text(debug)
for logical,name in [('internal/fsutil/fs.go','fs.go'),('internal/fsutil/stat.go','stat.go'),('engine/filesync/localfs.go','localfs.go'),('engine/filesync/mirror_metadata_mode.go','mode.go'),('cmd/engine/debug.go','debug.go'),('internal/fsutil/metadata_linux_test.go','metadata_test.go'),('engine/filesync/mirror_metadata_linux_test.go','filesync_test.go')]:
    overlay['Replace'][str(source/logical)]=str(root/name)
(root/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
subprocess.run(['gofmt','-w',*[str(root/n) for n in ['fs.go','stat.go','localfs.go','mode.go','debug.go']]],check=True)
print(root)
