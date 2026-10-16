from pathlib import Path
import hashlib,json,shutil
base=Path('/tmp/rust-cache-sipsma-review');root=base/'snapshot-gc-causal';root.mkdir(exist_ok=False)
source=Path('/tmp/dagger-filesync-snapshot-seeds')
previous=base/'usage-maps-real-engine'
replace=dict(json.loads((previous/'overlay.json').read_text())['Replace'])
manifest=json.loads((previous/'manifest.json').read_text())
for path,item in manifest.items():assert hashlib.sha256(Path(item['replacement']).read_bytes()).hexdigest()==item['sha256'],path
s=(source/'engine/server/snapshot_garbage.go').read_text()
s=s.replace('"sync/atomic"','"sync/atomic"\n "sync"\n "time"')
s=s.replace('"github.com/dagger/dagger/engine/slog"','"github.com/dagger/dagger/engine/slog"\n "github.com/dagger/dagger/engine/wcprof"')
s=s.replace('pending atomic.Bool','pending atomic.Bool\n // Diagnostic fields; production behavior is the zero value.\n deferred atomic.Bool\n diagnosticMu sync.Mutex\n diagnosticEvents []snapshotCollectionEvent')
old='func (g *snapshotGarbage) Collect(ctx context.Context) error {\n'
new='''func (g *snapshotGarbage) Collect(ctx context.Context) error {
 if g.deferred.Load() {
  started:=time.Now()
  g.pending.Store(true)
  g.recordCollection(snapshotCollectionEvent{Start:started,End:time.Now(),Deferred:true})
  return nil
 }
 return g.collect(ctx)
}

// collect also permits the diagnostic controller to force one collection while
// ordinary background collections are deferred. It never drops cache roots.
func (g *snapshotGarbage) collect(ctx context.Context) (rerr error) {
 started:=time.Now()
 ctx,op:=wcprof.BeginOp(ctx,wcprof.OpKindInternal,"snapshot.collect",wcprof.OpOpts{})
 defer func(){
  op.EndErr(rerr)
  event:=snapshotCollectionEvent{Start:started,End:time.Now()}
  if rerr!=nil {event.Error=rerr.Error()}
  g.recordCollection(event)
 }()
'''
assert s.count(old)==1;s=s.replace(old,new)
s+='''

type snapshotCollectionEvent struct {
 Start time.Time `json:"start"`
 End time.Time `json:"end"`
 Deferred bool `json:"deferred"`
 Error string `json:"error,omitempty"`
}
func (g *snapshotGarbage) recordCollection(event snapshotCollectionEvent) {
 g.diagnosticMu.Lock()
 defer g.diagnosticMu.Unlock()
 if len(g.diagnosticEvents)==256 {copy(g.diagnosticEvents,g.diagnosticEvents[1:]);g.diagnosticEvents=g.diagnosticEvents[:255]}
 g.diagnosticEvents=append(g.diagnosticEvents,event)
}
func (g *snapshotGarbage) diagnosticState() map[string]any {
 g.diagnosticMu.Lock()
 events:=append([]snapshotCollectionEvent(nil),g.diagnosticEvents...)
 g.diagnosticMu.Unlock()
 return map[string]any{"deferred":g.deferred.Load(),"pending":g.pending.Load(),"events":events}
}
'''
(root/'snapshot_garbage.go').write_text(s);replace[str(source/'engine/server/snapshot_garbage.go')]=str(root/'snapshot_garbage.go')
s=(source/'engine/server/gc.go').read_text().replace('"github.com/dagger/dagger/engine/config"','"github.com/dagger/dagger/engine/config"\n "github.com/dagger/dagger/engine/wcprof"')
s=s.replace('func (srv *Server) gcLocked(ctx context.Context, reason localCacheGCReason) error {','''func (srv *Server) gcLocked(ctx context.Context, reason localCacheGCReason) (rerr error) {
 ctx,op:=wcprof.BeginOp(ctx,wcprof.OpKindInternal,"engine.gc",wcprof.OpOpts{Ident:fmt.Sprint(reason)})
 defer func(){op.EndErr(rerr)}()''')
s=s.replace('rerr := srv.pruneLocalCacheLocked(ctx, reason)','rerr = srv.pruneLocalCacheLocked(ctx, reason)')
(root/'gc.go').write_text(s);replace[str(source/'engine/server/gc.go')]=str(root/'gc.go')
(root/'controller.go').write_text('''package server

import (
 "context"
 "errors"
 "fmt"
 "os"
 "path/filepath"
 "time"

 "github.com/containerd/containerd/v2/core/leases"
 "github.com/containerd/containerd/v2/pkg/namespaces"
 cerrdefs "github.com/containerd/errdefs"
 bkcache "github.com/dagger/dagger/engine/snapshots"
 "github.com/dagger/dagger/engine/wcprof"
)

// Diagnostic only. All mutation is limited to collector mode or a new scratch
// snapshot; no prune policy or existing cache root is removed by this endpoint.
func (srv *Server) SnapshotCollectionDiagnostic(ctx context.Context, action string, deferred, drain bool, files int, snapshotID string) (_ map[string]any, rerr error) {
 if action=="status" {
  status:=srv.snapshotGarbage.diagnosticState()
  if snapshotID!="" {
   _,err:=srv.containerdMetaDB.Snapshotter(srv.snapshotterName).Stat(namespaces.WithNamespace(ctx,"dagger"),snapshotID)
   if err!=nil && !cerrdefs.IsNotFound(err) {return nil,err}
   status["snapshot_exists"]=err==nil
  }
  return status,nil
 }
 srv.gcmu.Lock()
 defer srv.gcmu.Unlock()
 started:=time.Now()
 ctx,op:=wcprof.BeginOp(ctx,wcprof.OpKindInternal,"gc.diagnostic."+action,wcprof.OpOpts{})
 defer func(){op.EndErr(rerr)}()
 switch action {
 case "mode":
  srv.snapshotGarbage.deferred.Store(deferred)
  if drain {
   if err:=srv.snapshotGarbage.collect(ctx);err!=nil {return nil,err}
  }
  return srv.snapshotGarbage.diagnosticState(),nil
 case "collect":
  if err:=srv.snapshotGarbage.collect(ctx);err!=nil {return nil,err}
  return map[string]any{"seconds":time.Since(started).Seconds()},nil
 case "account":
  result,err:=srv.engineCache.MeasureUsageDiagnostic(ctx,false)
  if err!=nil {return nil,err}
  return result,nil
 case "prepare":
  if !srv.snapshotGarbage.deferred.Load() {return nil,fmt.Errorf("defer ordinary collections before preparing scratch garbage")}
  if files<0 || files>100000 {return nil,fmt.Errorf("files must be between0 and100000")}
  owner,err:=srv.leaseManager.Create(ctx,leases.WithRandomID(),bkcache.MakeTemporary)
  if err!=nil {return nil,err}
  defer func(){rerr=errors.Join(rerr,srv.workerCache.RemoveLease(context.Background(),owner.ID))}()
  ctx=leases.WithLease(ctx,owner.ID)
  mutable,err:=srv.workerCache.New(ctx,nil)
  if err!=nil {return nil,err}
  defer func(){rerr=errors.Join(rerr,mutable.Release(context.Background()))}()
  mounts,err:=mutable.Mount(ctx,false)
  if err!=nil {return nil,err}
  mounter:=bkcache.LocalMounter(mounts)
  directory,err:=mounter.Mount()
  if err!=nil {return nil,err}
  mounted:=true
  defer func(){if mounted {rerr=errors.Join(rerr,mounter.Unmount())}}()
  for i:=0;i<files;i++ {
   folder:=filepath.Join(directory,fmt.Sprintf("group-%04d",i/100))
   if i%100==0 {if err:=os.MkdirAll(folder,0755);err!=nil {return nil,err}}
   if err:=os.WriteFile(filepath.Join(folder,fmt.Sprintf("file-%06d",i)),[]byte("gc diagnostic\\n"),0644);err!=nil {return nil,err}
  }
  if err:=mounter.Unmount();err!=nil {return nil,err};mounted=false
  ref,err:=mutable.Commit(ctx)
  if err!=nil {return nil,err}
  if err:=srv.workerCache.AttachLease(ctx,owner.ID,ref.SnapshotID());err!=nil {return nil,errors.Join(err,ref.Release(ctx))}
  id:=ref.SnapshotID()
  if err:=ref.Release(ctx);err!=nil {return nil,err}
  return map[string]any{"snapshot_id":id,"files":files,"seconds":time.Since(started).Seconds()},nil
 default:return nil,fmt.Errorf("unknown diagnostic action %q",action)
 }
}
''')
replace[str(source/'engine/server/snapshot_collection_diagnostic.go')]=str(root/'controller.go')
s=Path(replace[str(source/'cmd/engine/debug.go')]).read_text()
needle='\tm := http.NewServeMux()'
new=needle+'''
 m.HandleFunc("/debug/snapshot-collection",func(w http.ResponseWriter,r *http.Request){
  action:=r.URL.Query().Get("action")
  if r.Method==http.MethodGet {action="status"} else if r.Method!=http.MethodPost {http.Error(w,"GET or POST required",405);return}
  deferred,err:=strconv.ParseBool(r.URL.Query().Get("deferred"));if err!=nil && action=="mode" {http.Error(w,err.Error(),400);return}
  files,_:=strconv.Atoi(r.URL.Query().Get("files"))
  result,err:=eng.SnapshotCollectionDiagnostic(r.Context(),action,deferred,r.URL.Query().Get("drain")=="true",files,r.URL.Query().Get("snapshot"))
  if err!=nil {http.Error(w,err.Error(),500);return}
  w.Header().Set("Content-Type","application/json");_ = json.NewEncoder(w).Encode(result)
 })'''
assert s.count(needle)==1;s=s.replace(needle,new)
(root/'debug.go').write_text(s);replace[str(source/'cmd/engine/debug.go')]=str(root/'debug.go')
(root/'deferred_test.go').write_text('''package server

import (
 "context"
 "testing"

 "github.com/stretchr/testify/require"
 "github.com/dagger/dagger/engine/snapshots/testutil"
)

func TestSnapshotCollectionDiagnosticPreservesPending(t *testing.T) {
 // A nil DB proves a deferred request never touches containerd.
 garbage:=&snapshotGarbage{}
 garbage.deferred.Store(true)
 require.NoError(t,garbage.Collect(context.Background()))
 require.True(t,garbage.pending.Load())
 require.True(t,garbage.diagnosticState()["deferred"].(bool))
}

func TestSnapshotCollectionDiagnosticDrainPreservesLeasedSnapshot(t *testing.T) {
 store:=testutil.NewStore(t)
 ctx:=context.Background()
 garbage:=newSnapshotGarbage(store.DB)
 kept,_:=store.Build(t,nil,"kept","kept data")
 released,owner:=store.Build(t,nil,"released","released data")
 id:=released.SnapshotID()
 require.NoError(t,released.Release(ctx))
 require.NoError(t,store.Manager.RemoveLease(ctx,owner))
 garbage.deferred.Store(true)
 require.NoError(t,garbage.CollectIfPending(ctx))
 requireSnapshotExists(t,store,id)
 require.True(t,garbage.pending.Load())
 garbage.deferred.Store(false)
 require.NoError(t,garbage.CollectIfPending(ctx))
 requireSnapshotCollected(t,store,id)
 testutil.CheckFile(t,kept,"kept","kept data")
}
''')
replace[str(source/'engine/server/snapshot_collection_diagnostic_test.go')]=str(root/'deferred_test.go')
(root/'overlay.json').write_text(json.dumps({'Replace':replace},indent=2)+'\n')
for name in ['engine.go.mod','engine.go.sum']:shutil.copy(previous/name,root/name)
print(root)
