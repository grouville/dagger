from pathlib import Path
import json,hashlib,difflib,subprocess
HERE=Path(__file__).resolve().parent
ROOT=Path('/home/dagger/dag')
MOD=Path('/tmp/dagger-go-kyle-latest')
sha=lambda b:hashlib.sha256(b).hexdigest()
base=(ROOT/'core/modfunc.go').read_text()
old='''		var result dagql.AnyObjectResult
		if err := srv.Select(mainCtx, addr, &result,
			dagql.Selector{
				Field: gqlFieldName(typename),
			},
		); err != nil {
			return nil, ud.errorf(err, "resolve object (%q)", typename)
		}
'''
new='''        // Address arguments hold the caller-bound address itself. Resolving
        // its target here would both require a nonexistent Address.address
        // field and prevent the module from choosing when to consume it.
        var result dagql.AnyObjectResult = addr
        if typename != "Address" {
            if err := srv.Select(mainCtx, addr, &result,
                dagql.Selector{Field: gqlFieldName(typename)},
            ); err != nil {
                return nil, ud.errorf(err, "resolve object (%q)", typename)
            }
        }
'''
assert base.count(old)==1
(HERE/'source/core/modfunc.go').write_text(base.replace(old,new))
s=(MOD/'go.dang').read_text()
s=s.replace('''  base: Container

  new(''','''  base: Container

  """
  Custom Go base address. Its Container is resolved only when preparing an
  execution container, in the workspace where the address was configured.
  """
  baseAddress: Address

  new(''',1)
s=s.replace('''    mountPath: String = null,
''','''    mountPath: String = null,
    """
    Address of a custom Go base. Resolved only for execution, so discovery
    does not run its producer. Cannot be combined with base. The target must
    return a Container with a Go toolchain; its errors surface when used.
    """
    baseAddress: Address = null,
''',1)
s=s.replace('''    } else {
      self.warnings = if (version != null and base != null) {''','''    } else if (base != null and baseAddress != null) {
      raise "base and baseAddress cannot both be set"
    } else {
      self.warnings = if (version != null and (base != null or baseAddress != null)) {''',1)
s=s.replace('''            + "\\\" is ignored because base was set: the base image supplies its own Go toolchain",''','''            + "\\\" is ignored because " + (if (base != null) { "base" } else { "baseAddress" })
            + " was set: the base image supplies its own Go toolchain",''',1)
s=s.replace('''      self.version = if (base == null) { version } else { null }
      self.base = base''','''      self.version = if (base == null and baseAddress == null) { version } else { null }
      self.base = base
      self.baseAddress = baseAddress''',1)
s=s.replace('''      baseImage: base,
''','''      baseImage: base,
      baseImageAddress: baseAddress,
''',1)
s=s.replace('''  let baseImage: Container
''','''  let baseImage: Container

  # Keep the caller-bound address; do not resolve during module/test discovery.
  let baseImageAddress: Address
''',1)
s=s.replace('''    if (baseImage == null) { toolchainVersion(ws) } else { null }''','''    if (baseImage == null and baseImageAddress == null) { toolchainVersion(ws) } else { null }''',1)
s=s.replace('''  base(ws: Workspace!): Container! {
    prepareBase(
      if (baseImage == null) {
        gomod.goContainer(toolchainVersion(ws))
      } else {
        gomod.withGoCaches(baseImage.withoutEntrypoint)
      },
    )
  }''','''  base(ws: Workspace!): Container! {
    let customBase = if (baseImageAddress == null) { baseImage } else { baseImageAddress.container }
    prepareBase(
      if (customBase == null) {
        gomod.goContainer(toolchainVersion(ws))
      } else {
        gomod.withGoCaches(customBase.withoutEntrypoint)
      },
    )
  }''',1)
assert 'baseImageAddress.container' in s
assert s.count('baseImageAddress.container')==1
(HERE/'module/go.dang').write_text(s)
subprocess.run(['/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/gofmt','-w',*[str(p)for p in (HERE/'source').rglob('*.go')]],check=True)
manifest={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'module_base':'1784ff37eb3dd1aacab7aaff91b1d86e311cc8de','status':'source-only; no parsing, compilation, tests, engine or Cloud calls','originals':{},'sources':{}}
for label,source_root,oldroot in [('engine',HERE/'source',ROOT),('module',HERE/'module',MOD)]:
    patch=[]
    for p in sorted(source_root.rglob('*')):
        if not p.is_file():continue
        name=str(p.relative_to(source_root));oldp=oldroot/name;before=oldp.read_bytes() if oldp.exists() else b'';after=p.read_bytes()
        manifest['originals'][label+'/'+name]=sha(before)if before else None
        manifest['sources'][label+'/'+name]=sha(after)
        patch+=difflib.unified_diff(before.decode().splitlines(True),after.decode().splitlines(True),fromfile='a/'+name if before else '/dev/null',tofile='b/'+name)
    (HERE/(label+'.patch')).write_text(''.join(patch))
prod={str(ROOT/str(p.relative_to(HERE/'source'))):str(p) for p in (HERE/'source').rglob('*.go') if not p.name.endswith('_test.go')}
tests={str(ROOT/str(p.relative_to(HERE/'source'))):str(p) for p in (HERE/'source').rglob('*.go')}
(HERE/'source-overlay.json').write_text(json.dumps({'Replace':prod},indent=2)+'\n')
(HERE/'test-overlay.json').write_text(json.dumps({'Replace':tests},indent=2)+'\n')
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'engine_patch_sha256':sha((HERE/'engine.patch').read_bytes()),'module_patch_sha256':sha((HERE/'module.patch').read_bytes()),'status':manifest['status']}))
