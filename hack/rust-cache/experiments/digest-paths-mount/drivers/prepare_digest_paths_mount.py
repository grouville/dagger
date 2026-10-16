from pathlib import Path
import hashlib
import json
import shutil
import subprocess

base = Path('/tmp/rust-cache-sipsma-review')
root = base / 'digest-paths-mount'
root.mkdir(exist_ok=False)
source = Path('/tmp/dagger-filesync-snapshot-seeds')
previous = base / 'artifact-metadata-fields'
overlay = json.loads((previous / 'engine-overlay.json').read_text())
for name in ['engine.go.mod', 'engine.go.sum']:
    shutil.copyfile(previous / name, root / name)

(root / 'batch.go').write_text('''package core

import (
    "context"
    "errors"
    "fmt"
    "io/fs"
    "net/http"
    "encoding/json"
    "os"
    "path"
    "strconv"
    "sync/atomic"
    "syscall"

    "github.com/containerd/containerd/v2/core/mount"
    containerdfs "github.com/containerd/continuity/fs"
    "github.com/dagger/dagger/dagql"
    bkcontenthash "github.com/dagger/dagger/engine/contenthash"
)

var digestPathsOneMount atomic.Bool

// DigestPaths shares snapshot evaluation and stat mounts across a batch.
// Results preserve DigestPath's order, validation and canonical hash format.
func (dir *Directory) DigestPaths(ctx context.Context, self dagql.ObjectResult[*Directory], paths []string) ([]string, error) {
    if !digestPathsOneMount.Load() || len(paths) < 2 {
        digests := make([]string, len(paths))
        for i, subdir := range paths {
            digest, err := dir.DigestPath(ctx, self, subdir)
            if err != nil { return nil, err }
            digests[i] = digest
        }
        return digests, nil
    }
    snapshot, err := dir.Snapshot.GetOrEval(ctx, self.Result)
    if err != nil { return nil, fmt.Errorf("failed to evaluate directory: %w", err) }
    if snapshot == nil { return nil, fmt.Errorf("failed to evaluate null directory") }
    base, err := dir.Dir.GetOrEval(ctx, self.Result)
    if err != nil { return nil, fmt.Errorf("failed to get directory path: %w", err) }
    parentCall, err := self.ResultCall()
    if err != nil { return nil, err }
    digests := make([]string, len(paths))
    err = MountRef(ctx, snapshot, func(root string, _ *mount.Mount) error {
        for i, subdir := range paths {
            if err := ctx.Err(); err != nil { return err }
            selected := base
            if cleanDotsAndSlashes(subdir) != "" {
                selected = path.Join(base, subdir)
                resolved, statErr := containerdfs.RootPath(root, selected)
                if statErr == nil {
                    info, err := os.Stat(resolved)
                    statErr = TrimErrPathPrefix(err, root)
                    if statErr == nil && !info.IsDir() {
                        return notADirectoryError{fmt.Errorf("path %s is a file, not a directory", subdir)}
                    }
                }
                if statErr != nil {
                    if errors.Is(statErr, fs.ErrNotExist) {
                        statErr = &os.PathError{Op: "stat", Path: subdir, Err: syscall.ENOENT}
                    }
                    return RestoreErrPath(statErr, subdir)
                }
                if parentCall.ContentDigest() != "" {
                    digest, err := GetContentHashFromDirectory(ctx, snapshot, selected)
                    if err != nil { return err }
                    digests[i] = digest.String()
                    continue
                }
            }
            digest, err := bkcontenthash.Checksum(ctx, snapshot, selected, bkcontenthash.ChecksumOpts{})
            if err != nil { return fmt.Errorf("failed to compute digest: %w", err) }
            digests[i] = digest.String()
        }
        return nil
    })
    return digests, err
}

func DigestPathsMountDiagnostic(w http.ResponseWriter, r *http.Request) {
    if r.Method == http.MethodPost {
        enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
        if err != nil { http.Error(w, err.Error(), 400); return }
        digestPathsOneMount.Store(enabled)
    } else if r.Method != http.MethodGet { http.Error(w, "GET or POST required", 405); return }
    w.Header().Set("Content-Type", "application/json")
    _ = json.NewEncoder(w).Encode(map[string]bool{"enabled": digestPathsOneMount.Load()})
}
''')

logical = str(source / 'core/schema/directory.go')
schema = Path(overlay['Replace'][logical]).read_text()
start = schema.index('\tdigests := make([]string, len(args.Paths))', schema.index('func (s *directorySchema) digests('))
end = schema.index('\n}', start)
schema = schema[:start] + '''\tdigests, err := parent.Self().DigestPaths(ctx, parent, args.Paths)
    if err != nil { return nil, err }
    return dagql.NewStringArray(digests...), nil''' + schema[end:]
(root / 'directory-schema.go').write_text(schema)
debug = Path(overlay['Replace'][str(source / 'cmd/engine/debug.go')]).read_text()
assert debug.count('m := http.NewServeMux()') == 1
debug = debug.replace('m := http.NewServeMux()', 'm := http.NewServeMux()\n m.HandleFunc("/debug/digest-paths-mount", core.DigestPathsMountDiagnostic)')
if '"github.com/dagger/dagger/core"' not in debug:
    debug = debug.replace('import (', 'import (\n "github.com/dagger/dagger/core"', 1)
(root / 'debug.go').write_text(debug)
overlay['Replace'][str(source / 'core/directory_digest_paths.go')] = str(root / 'batch.go')
overlay['Replace'][logical] = str(root / 'directory-schema.go')
overlay['Replace'][str(source / 'cmd/engine/debug.go')] = str(root / 'debug.go')
subprocess.run(['gofmt', '-w', str(root / 'batch.go'), str(root / 'directory-schema.go'), str(root / 'debug.go')], check=True)
(root / 'engine-overlay.json').write_text(json.dumps(overlay, indent=2) + '\n')
(root / 'manifest.json').write_text(json.dumps({k:dict(replacement=v, sha256=hashlib.sha256(Path(v).read_bytes()).hexdigest()) for k,v in overlay['Replace'].items()},indent=2)+'\n')
print('Prepared shared-mount batch; default uses original DigestPath loop')
