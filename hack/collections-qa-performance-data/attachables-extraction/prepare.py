from pathlib import Path
import difflib, hashlib, json, subprocess
ROOT=Path('/home/dagger/dag'); HERE=Path(__file__).resolve().parent
NEW='github.com/dagger/dagger/engine/session/attachables'
sha=lambda b:hashlib.sha256(b).hexdigest()
inputs={}; replacements={}; originals={}
def read(path):
 b=(ROOT/path).read_bytes(); inputs[path]=sha(b);return b.decode()
def emit(path,text,original=None):
 out=HERE/'source'/path;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text)
 replacements[str(ROOT/path)]=str(out);originals[path]=original if original is not None else ''
client=read('engine/client/client.go')
begin=client.index('func ConnectSessionAttachables(');end=client.index('func (c *Client) daggerConnect(',begin)
server=client[begin:end]
server_imports='''package attachables

import (
 "bufio"
 "context"
 "fmt"
 "io"
 "net"
 "net/http"
 "net/url"

 "github.com/dagger/dagger/engine"
 telemetry "github.com/dagger/otel-go"
 "go.opentelemetry.io/otel/propagation"
 "golang.org/x/net/http2"
 "google.golang.org/grpc"
 "google.golang.org/grpc/health"
 "google.golang.org/grpc/health/grpc_health_v1"
)

// Preserve the existing provider instrumentation scope across the package move.
const InstrumentationLibrary = "dagger.io/engine.client"

type SessionAttachable interface {
 Register(*grpc.Server)
}

'''
emit('engine/session/attachables/server.go',server_imports+server)
wrappers='''// SessionAttachablesServer remains an alias for compatibility with client consumers.
type SessionAttachablesServer = attachables.SessionAttachablesServer

func ConnectSessionAttachables(ctx context.Context, conn net.Conn, headers http.Header, providers ...SessionAttachable) (*SessionAttachablesServer, error) {
 return attachables.ConnectSessionAttachables(ctx, conn, headers, providers...)
}

func NewSessionAttachablesServer(ctx context.Context, conn net.Conn, providers ...SessionAttachable) *SessionAttachablesServer {
 return attachables.NewSessionAttachablesServer(ctx, conn, providers...)
}

'''
newclient=client[:begin]+wrappers+client[end:]
old_iface='type SessionAttachable interface {\n\tRegister(*grpc.Server)\n}'
assert newclient.count(old_iface)==1
newclient=newclient.replace(old_iface,'type SessionAttachable = attachables.SessionAttachable')
for imp in ['bufio','google.golang.org/grpc/health','google.golang.org/grpc/health/grpc_health_v1']:
 needle='\t"'+imp+'"\n';assert newclient.count(needle)==1;newclient=newclient.replace(needle,'')
newclient=newclient.replace('"github.com/dagger/dagger/engine/session/git"','"'+NEW+'"\n\t"github.com/dagger/dagger/engine/session/git"')
emit('engine/client/client.go',newclient,client)
for name in ['filesync','socket']:
 old=read('engine/client/'+name+'.go');assert old.startswith('package client\n');emit('engine/session/attachables/'+name+'.go',old.replace('package client','package attachables',1))
compat_filesync='''package client

import "github.com/dagger/dagger/engine/session/attachables"

type Filesyncer = attachables.Filesyncer
type FilesyncSource = attachables.FilesyncSource
type FilesyncTarget = attachables.FilesyncTarget
type FilesyncSourceProxy = attachables.FilesyncSourceProxy
type FilesyncTargetProxy = attachables.FilesyncTargetProxy

func NewFilesyncer() (Filesyncer, error) { return attachables.NewFilesyncer() }
'''
emit('engine/client/filesync.go',compat_filesync,(ROOT/'engine/client/filesync.go').read_text())
compat_socket='''package client

import (
 "github.com/dagger/dagger/engine/session/attachables"
 "github.com/dagger/dagger/internal/buildkit/session/sshforward"
)

type SocketProvider = attachables.SocketProvider
type SocketSessionProxy = attachables.SocketSessionProxy

func NewSocketSessionProxy(client sshforward.SSHClient) *SocketSessionProxy {
 return attachables.NewSocketSessionProxy(client)
}
'''
emit('engine/client/socket.go',compat_socket,(ROOT/'engine/client/socket.go').read_text())
main=read('cmd/init/main.go');needle='"github.com/dagger/dagger/engine/client"';assert main.count(needle)==1
emit('cmd/init/main.go',main.replace(needle,'client "'+NEW+'"'),main)
(HERE/'source-overlay.json').write_text(json.dumps({'Replace':replacements},indent=2)+'\n')
# Move tests that intentionally call package-private filesync helpers. Client lifetime tests stay in place.
tests=dict(replacements)
for name in ['filesync_test.go','filesync_parent_metadata_test.go']:
 old=read('engine/client/'+name)
 p=HERE/'tests'/'engine/session/attachables'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(old.replace('package client','package attachables',1));tests[str(ROOT/'engine/session/attachables'/name)]=str(p)
 stub=HERE/'tests'/'engine/client'/name;stub.parent.mkdir(parents=True,exist_ok=True);stub.write_text('package client\n');tests[str(ROOT/'engine/client'/name)]=str(stub)
for rel in ['engine/session/attachables/socket_extraction_test.go','engine/client/attachables_alias_test.go']:
 tests[str(ROOT/rel)]=str(HERE/'tests'/rel)
(HERE/'test-overlay.json').write_text(json.dumps({'Replace':tests},indent=2)+'\n')
# Formatting only, no compiler, module resolution or runtime.
gofmt=Path('/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt')
subprocess.run([str(gofmt),'-w',*sorted(set(tests.values()))],check=True)
patch=[]
for absolute,out in replacements.items():
 rel=str(Path(absolute).relative_to(ROOT));patch.extend(difflib.unified_diff(originals[rel].splitlines(True),Path(out).read_text().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
(HERE/'prototype.patch').write_text(''.join(patch))
(HERE/'manifest.json').write_text(json.dumps({'status':'source-only; not compiled or tested','head':'e6e723145e914680b9daea080046c55eb6ccc233','prepared_checkout_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'originals':inputs,'sources':{p:sha(Path(p).read_bytes())for p in sorted(set(tests.values()))},'new_package':NEW,'provider_logic':'filesync.go/socket.go unchanged apart from package declaration; server function bodies moved unchanged; secret/Git/network providers untouched','compatibility':'exported type aliases and constructor/server forwarding functions; reflected package path and old package-private access are not preserved'},indent=2)+'\n')
print(json.dumps({'production_overlay_files':len(replacements),'test_overlay_files':len(tests),'patch_sha256':sha((HERE/'prototype.patch').read_bytes())}))
