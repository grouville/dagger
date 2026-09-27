"""Prepare one NEW full-repository QA fixture. No Dagger/Docker invocation."""
from pathlib import Path
import argparse,hashlib,json,subprocess,tarfile
H=Path(__file__).resolve().parent;BASE=Path('/tmp/dagger-go-kyle-latest');SOURCE=Path('/tmp/collections-perf/go-base-address-v1');REV='1784ff37eb3dd1aacab7aaff91b1d86e311cc8de';W=H/'workspace-v3'
A=argparse.ArgumentParser();A.add_argument('--run',action='store_true');a=A.parse_args()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
if not a.run:print(json.dumps({'prepare_only':True,'revision':REV,'destination':str(W),'dagger_calls':0}));raise SystemExit
assert not W.exists() and not (H/'fixture-manifest-v3.json').exists()
freeze=json.loads((H/'source-manifest-v3.json').read_text())
for p,h in freeze['source_hashes'].items():assert sha(p)==h,p
assert subprocess.check_output(['git','rev-parse',REV+'^{commit}'],cwd=BASE,text=True).strip()==REV
archive=H/'upstream-v3.private.tar'
with archive.open('xb')as f:subprocess.run(['git','archive','--format=tar',REV],cwd=BASE,stdout=f,check=True,timeout=30)
W.mkdir(mode=0o700)
with tarfile.open(archive)as t:t.extractall(W,filter='data')
for name in ['go.dang','.dagger/modules/go-dev/main.dang','testdata/go-module-custom-base/base-marker.txt']:
 (W/name).write_bytes((SOURCE/'module'/name).read_bytes())
(W/'.dagger/modules/go-dev/main.dang').write_bytes((H/'source/main-v3.dang').read_bytes())
assert sha(W/'go.dang')==freeze['candidate_go_sha256']
qa=W/'.dagger/modules/go-dev/main.dang';s=qa.read_text();before=s
old='''  let base: Container! {
    container
      .from("golang:1.26.1-alpine")''';new=old.replace('golang:1.26.1-alpine','golang:1.26-alpine@sha256:51a7c389a5ddaf82f527191a1e9bff9928655130a44e4975dd1d7e0acf59f1ae')
assert s.count(old)==1;s=s.replace(old,new)
address_start=s.index("  addressBase(ws: Workspace!): Container! {")
address_end=s.index("  baseAddressDiscoveryCheck(ws: Workspace!): Void @check {",address_start)
address_block=s[address_start:address_end]
assert address_block.count('.from("busybox:1.37.0")')==1
s=s[:address_start]+address_block.replace('.from("busybox:1.37.0")','.from("busybox:1.37@sha256:bdf57e528e45e4433820e045b29b4597825a1c9e38353532d90a01445013f82e")')+s[address_end:]
qa.write_text(s)
config='[modules.go-dev]\nsource = ".dagger/modules/go-dev"\nentrypoint = true\n'
(W/'dagger.toml').write_text(config)
subprocess.run(['git','init','-q',str(W)],check=True,timeout=10);subprocess.run(['git','-C',str(W),'add','-f','.'],check=True,timeout=10)
files={str(p.relative_to(W)):sha(p)for p in W.rglob('*')if p.is_file()and'.git'not in p.relative_to(W).parts}
manifest={'upstream_revision':REV,'archive_sha256':sha(archive),'source_manifest_sha256':sha(H/'source-manifest-v3.json'),'candidate_go_sha256':sha(W/'go.dang'),'qa_source_before_fixture_pins_sha256':hashlib.sha256(before.encode()).hexdigest(),'qa_source_with_fixture_pins_sha256':sha(qa),'workspace_config':config,'fixture_image_overrides_only':True,'files':files,'dagger_calls':0}
(H/'fixture-manifest-v3.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'prepared':str(W),'files':len(files),'candidate_go_sha256':sha(W/'go.dang')}))
