from pathlib import Path
import hashlib,json,subprocess

root=Path(__file__).parent
source=Path('/tmp/dagger-filesync-snapshot-seeds')
out=root/'default-cost'
out.mkdir(exist_ok=False)
original=(source/'internal/fsutil/fs.go').read_text()
walk=original[original.index('type fs struct {'):original.index('type Dir struct {')]
entry=original[original.index('type DirEntryInfo struct {'):]
reference='''//go:build linux
package fsutil
import (
    "context"
    "io"
    gofs "io/fs"
    "os"
    "path/filepath"
    "github.com/dagger/dagger/internal/fsutil/types"
    "github.com/pkg/errors"
)
'''+walk+entry
reference=reference.replace('type fs struct {','type referenceMetadataFS struct {').replace('(fs *fs)','(fs *referenceMetadataFS)').replace('DirEntryInfo','referenceMetadataDirEntryInfo').replace('mkstat(s.origpath, s.path, fi, s.seenFiles)','mkstat(s.origpath, s.path, fi, s.seenFiles, false)')
(out/'reference_test.go').write_text(reference)
bench=(root/'metadata_test.go').read_text()
bench=bench[:bench.index('func TestWalkMetadataOptions')]+bench[bench.index('func BenchmarkMirrorMetadataWalk'):]
bench=bench.replace('\n\t"reflect"','')
bench=bench.replace('\n\t"github.com/dagger/dagger/internal/fsutil/types"','')
bench=bench.replace('for _, skip := range []bool{false, true}', 'for _, reference := range []bool{false, true}')
bench=bench.replace('fmt.Sprintf("skip=%t", skip)','fmt.Sprintf("reference=%t", reference)')
bench=bench.replace('filesystem, err := NewFSWithOptions(root, FSOptions{SkipXattrs: skip})','filesystem, err := NewFS(root)\n                if reference { filesystem=&referenceMetadataFS{root:root} }')
(out/'benchmark_test.go').write_text(bench)
overlay=json.loads((root/'overlay.json').read_text())
overlay['Replace'][str(source/'internal/fsutil/metadata_linux_test.go')]=str(out/'benchmark_test.go')
overlay['Replace'][str(source/'internal/fsutil/metadata_reference_linux_test.go')]=str(out/'reference_test.go')
(out/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n')
(out/'reference.json').write_text(json.dumps(dict(source_file=str(source/'internal/fsutil/fs.go'),source_sha256=hashlib.sha256(original.encode()).hexdigest(),note='Frozen original walk and directory entry types, renamed to coexist with the candidate. Only the new private mkstat signature is adapted with skip=false; original layout and traversal are retained. Constructor validation is outside the timed loop.'),indent=2)+'\n')
subprocess.run(['gofmt','-w',str(out/'reference_test.go'),str(out/'benchmark_test.go')],check=True)
