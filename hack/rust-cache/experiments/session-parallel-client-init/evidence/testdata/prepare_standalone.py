from pathlib import Path
import difflib,hashlib,json,subprocess
root=Path(__file__).parent

def replace_once(source, before, after):
    assert source.count(before)==1,repr(before)
    return source.replace(before,after,1)

def transform(source):
    edits=[
      ('lifecycleMu sync.Mutex','lifecycleMu sync.RWMutex'),
      ('// active-clients API or the client-DB GC.\n\tlifecycleMu','// active-clients API or the client-DB GC. Nested client admission holds a\n\t// read lock; root admission and session transitions retain exclusive access.\n\tlifecycleMu'),
      ('\tengineUtilClient *engineutil.Client','\tengineUtilClientMu sync.Mutex\n\tengineUtilClient   *engineutil.Client'),
      ('\tstate   clientRuntimeState\n\tstateMu sync.RWMutex','\t// admissionMu serializes requests for this client before they enter scopeMu.\n\t// In particular, a request waiting for runtime initialization must not hold\n\t// scopeMu, which initialization itself can acquire through DagQL.\n\tadmissionMu sync.Mutex\n\n\tstate   clientRuntimeState\n\tstateMu sync.RWMutex'),
      ('// requires that sess.lifecycleMu is held\nfunc (srv *Server) initializeSessionEngineClient(ctx context.Context, sess *daggerSession) error {\n','// Callers hold sess.lifecycleMu, possibly for reading.\nfunc (srv *Server) initializeSessionEngineClient(ctx context.Context, sess *daggerSession) error {\n\tsess.engineUtilClientMu.Lock()\n\tdefer sess.engineUtilClientMu.Unlock()\n'),
      ('\tif !createdSession {\n\t\t// Fast, lock-free check:','\tsharedAdmission := !createdSession && !opts.RootClient\n\tif !createdSession {\n\t\t// Fast, lock-free check:'),
      ('\t\t\tsess.lifecycleMu.Unlock()\n\t\t}\n\t}\n\tdefer func() {','\t\t\tif sharedAdmission {\n\t\t\t\tsess.lifecycleMu.RUnlock()\n\t\t\t} else {\n\t\t\t\tsess.lifecycleMu.Unlock()\n\t\t\t}\n\t\t}\n\t}\n\tdefer func() {'),
      ('\tparentClientIDs, err := sess.parentClientIDsForRegistration(clientID, opts.ParentClientID, opts.RootClient)','\tif sharedAdmission && clientExists {\n\t\tclient.admissionMu.Lock()\n\t\tdefer client.admissionMu.Unlock()\n\t}\n\n\tparentClientIDs, err := sess.parentClientIDsForRegistration(clientID, opts.ParentClientID, opts.RootClient)'),
    ]
    for before,after in edits:source=replace_once(source,before,after)
    needle='\t\tsess.lifecycleMu.Lock()\n'
    assert source.count(needle)==1
    source=source.replace(needle,'\t\tif sharedAdmission {\n\t\t\tsess.lifecycleMu.RLock()\n\t\t} else {\n\t\t\tsess.lifecycleMu.Lock()\n\t\t}\n',1)
    return source

go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt'
def fmt(source):return subprocess.check_output([go],input=source.encode()).decode()
assert fmt(transform((root/'before-session.go').read_text()))==(root/'after-session.go').read_text()
source=Path('/tmp/dagger-go-real-repository-main')
original=(source/'engine/server/session.go').read_text()
changed=fmt(transform(original))
(root/'upstream-before-session.go').write_text(original)
(root/'upstream-after-session.go').write_text(changed)
patch=''.join(difflib.unified_diff(original.splitlines(True),changed.splitlines(True),fromfile='a/engine/server/session.go',tofile='b/engine/server/session.go'))
test=(root/'parallel_client_init_test.go').read_text()
patch+=''.join(difflib.unified_diff([],test.splitlines(True),fromfile='/dev/null',tofile='b/engine/server/parallel_client_init_test.go'))
(root/'standalone.patch').write_text(patch)
for arm,file in [('before','upstream-before-session.go'),('after','upstream-after-session.go')]:
    overlay={'Replace':{
        str(source/'engine/server/session.go'):str(root/file),
        str(source/'engine/server/parallel_client_init_test.go'):str(root/'parallel_client_init_test.go'),
    }}
    (root/('upstream-overlay-'+arm+'.json')).write_text(json.dumps(overlay,indent=2)+'\n')
identity=dict(source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip(),
 files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['before-session.go','after-session.go','controlled-session.go','upstream-before-session.go','upstream-after-session.go','parallel_client_init_test.go']},
 diagnostic_transform_matches_tested_candidate=True)
(root/'source-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
print('Standalone patch prepared on clean upstream source; transformations match the tested diagnostic candidate.')
