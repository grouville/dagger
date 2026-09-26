#!/usr/bin/env python3
"""Build/package outside all timed benchmark windows. Never starts an engine."""
import hashlib, json, os, subprocess
from pathlib import Path
BASE=Path('/tmp/collections-perf/post-rebase-io')
DEST=BASE/'cold-scratch-audit'
ROOT=Path('/home/dagger/dag')
BINARY=DEST/'engine-scratch-verified'
IMAGE='localhost/dagger-engine.collections-main-io:scratch-audit'
CONTAINER='dagger-engine.collections-scratch-image-prep'
def run(args,**kwargs):
 return subprocess.check_output(args,text=True,**kwargs).strip()
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
 return h.hexdigest()
# Avoid accidental inclusion of another experiment in this build. CLI changes
# are also prohibited, as cmd/engine links the same module packages.
assert not run(['git','status','--porcelain'],cwd=ROOT),'Rebuild requires reviewed clean source; overlay experiments remain outside the tree.'
ref=run(['git','rev-parse','HEAD'],cwd=ROOT)
overlay=BASE/'scratch-overlay.json'
replace=json.loads(overlay.read_text())['Replace']
metadata={'base_commit':ref,'build_overlay':json.loads(overlay.read_text()),
 'overlay_sha256':{p:digest(p) for p in replace.values()},
 'modfile_sha256':digest(BASE/'build.mod'),
 'telemetry_source_sha256':{p:digest(ROOT/p) for p in ['engine/telemetry/callpayloadbatch.go','engine/server/session_cloud_telemetry.go']}}
cmd=['go','build','-buildvcs=false','-modfile='+str(BASE/'build.mod'),'-overlay='+str(overlay),'-o',str(BINARY),'./cmd/engine']
metadata['build_command']=cmd
with (DEST/'build.log').open('wb') as log:
 subprocess.run(cmd,cwd=ROOT,env=dict(os.environ,CGO_ENABLED='0'),stdout=log,stderr=subprocess.STDOUT,check=True)
metadata['binary_sha256']=digest(BINARY)
metadata['binary_buildinfo']=run(['go','version','-m',str(BINARY)])
assert run(['git','rev-parse','HEAD'],cwd=ROOT)==ref
assert not run(['git','status','--porcelain'],cwd=ROOT),'Source changed during build'
assert subprocess.run(['docker','container','inspect',CONTAINER],capture_output=True).returncode!=0,'Preparation container already exists'
assert subprocess.run(['docker','image','inspect',IMAGE],capture_output=True).returncode!=0,'Preparation image already exists'
base='localhost/dagger-engine.collections-main-io:candidate'
metadata['base_image']=run(['docker','image','inspect','--format','{{.Id}}',base])
run(['docker','create','--name',CONTAINER,base])
run(['docker','cp',str(BINARY),CONTAINER+':/usr/local/bin/dagger-engine'])
metadata['image']=run(['docker','commit',CONTAINER,IMAGE])
# Retain the never-started preparation container and every resulting volume.
(DEST/'prepared.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps({'image':metadata['image'],'binary_sha256':metadata['binary_sha256']}))
