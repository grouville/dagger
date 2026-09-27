from pathlib import Path
import hashlib,json,subprocess,shutil
H=Path(__file__).resolve().parent;B=H/'builds';R=Path('/home/dagger/dag');P=Path('/tmp/collections-perf/artifact-static-prune-v1/builds');D=Path('/tmp/collections-perf/artifact-tree-profile-v1')
B.mkdir(exist_ok=True);(B/'inputs').mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
parent=json.loads((P/'recipe.json').read_text());manifest=json.loads((H/'manifest.json').read_text());validation=json.loads((H/'validation-v2/results.json').read_text())
assert all(s['passed']for s in validation['stages'])
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()==parent['source_head']==manifest['source_head']
assert sha(R/'core/modfunc.go')==manifest['originals']['engine/core/modfunc.go']
assert sha(R/'core/modtree.go')==json.loads((D/'manifest.json').read_text())['baseline_sha256']
replace={};inputs={};origins={}
for i,(logical,physical)in enumerate(json.loads((P/'baseline-overlay.json').read_text())['Replace'].items()):
 if not physical:replace[logical]='';continue
 assert sha(physical)==parent['inputs'][physical]
 target=B/'inputs'/('base-%02d-'%i+Path(physical).name);shutil.copyfile(physical,target)
 replace[logical]=str(target);inputs[str(target)]=sha(target);origins[str(target)]={'path':physical,'sha256':sha(physical)}
for logical,physical in [(str(R/'core/modfunc.go'),H/'source/core/modfunc.go'),(str(R/'core/modtree.go'),D/'modtree.go')]:
 target=B/'inputs'/Path(logical).name;shutil.copyfile(physical,target);replace[logical]=str(target);inputs[str(target)]=sha(target);origins[str(target)]={'path':str(physical),'sha256':sha(physical)}
for name in ('engine.mod','engine.sum'):
 assert sha(P/name)==parent['inputs'][str(P/name)]
 shutil.copyfile(P/name,B/name);inputs[str(B/name)]=sha(B/name)
save(B/'source-overlay.json',{'Replace':replace});inputs[str(B/'source-overlay.json')]=sha(B/'source-overlay.json')
GO='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
cmd=[GO,'build','-mod=readonly','-modfile='+str(B/'engine.mod'),'-buildvcs=true','-overlay='+str(B/'source-overlay.json'),'-o',str(B/'engine-address'),'./cmd/engine']
# This known local replacement is the already-frozen dependency used in the parent engine.
external_root=Path('/tmp/collections-perf/syntax-isolated/dang');external={}
for name in subprocess.check_output(['rg','--files','--hidden','-g','*.go','-g','go.mod','-g','go.sum','-g','*.ebnf','-g','*.peg'],cwd=external_root,text=True).splitlines():
 p=external_root/name;external[str(p)]=sha(p)
status=subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=normal'],cwd=R,text=True).splitlines()
assert all(line[3:].startswith('hack/') for line in status),status
recipe={'source_head':parent['source_head'],'behavior_source_head':parent['behavior_source_head'],'source_dirty_state':status,'allowed_dirty_prefixes':['hack/'],'parent_recipe_sha256':sha(P/'recipe.json'),'parent_manifest_sha256':sha(P/'manifest.json'),'parent_baseline_overlay_sha256':sha(P/'baseline-overlay.json'),'baseline_ancestry_engine':parent['parent_engine'],'baseline_rebuilt_engine':json.loads((P/'manifest.json').read_text())['baseline_engine'],'cli':parent['cli'],'address_manifest_sha256':sha(H/'manifest.json'),'validation_sha256':sha(H/'validation-v2/results.json'),'profile_manifest_sha256':sha(D/'manifest.json'),'profile_patch_sha256':sha(D/'prototype.patch'),'go':{'path':GO,'sha256':sha(GO)},'inputs':inputs,'origins':origins,'external_dependency_inputs':external,'source_originals':{str(R/'core/modfunc.go'):manifest['originals']['engine/core/modfunc.go'],str(R/'core/modtree.go'):json.loads((D/'manifest.json').read_text())['baseline_sha256']},'environment':{**parent['environment'],'GOENV':'off','GOFLAGS':'','DO_NOT_TRACK':'1'},'command':cmd,'scope':'One common engine for legacy base versus optional baseAddress module comparison. Frozen ec6 behavior + generic UserDefault Address fix + fixed-label opt-in artifact-tree wcprof boundaries only. No artifact pruning, helper extraction, split init, new transports or held telemetry prototypes. Existing clean baseline is provenance, not a timing arm.','runtime_commands':0,'cloud_commands':0}
save(B/'build-recipe.json',recipe);print(json.dumps({'recipe':str(B/'build-recipe.json'),'sha256':sha(B/'build-recipe.json'),'expected_vcs_modified':bool(status),'overlay_entries':len(replace),'external_inputs':len(external)}))
