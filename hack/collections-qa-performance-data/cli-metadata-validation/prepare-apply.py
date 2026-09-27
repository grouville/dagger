from pathlib import Path
import difflib,hashlib,json,shutil
H=Path(__file__).resolve().parent; P=H.parent/'collection-closure-v1/apply-ready'; A=H/'apply-ready'; A.mkdir(exist_ok=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
m=json.loads((P/'manifest.json').read_text())
shutil.copyfile(P/'01-collection-closure.patch',A/'01-collection-closure.patch')
patch=(P/'02-cli-metadata-json-after-closure.patch').read_text()
for path,before,after in [('engine/server/session_workspaces.go',H/'session_workspaces.original.go',H/'session_workspaces.frozen.go'),('engine/server/typedef_json_demand_test.go',None,H/'typedef_json_demand_test.go')]:
    patch+=''.join(difflib.unified_diff(before.read_text().splitlines(keepends=True)if before else [],after.read_text().splitlines(keepends=True),fromfile='a/'+path if before else '/dev/null',tofile='b/'+path))
    m['json_files_after_closure'].append({'path':path,'before_sha256':sha(before)if before else None,'after_sha256':sha(after),'tested_source':str(after)})
(A/'02-cli-metadata-json-after-closure.patch').write_text(patch)
m['request_demand_validation']=json.loads((H/'validation.json').read_text())
m['notes'].append('JSON patch now includes engine request-demand routing, matching scoped/unscoped old metadata behavior; unscoped live collection proof pending new engine runtime.')
m['patches']={f.name:sha(f)for f in A.glob('*.patch')}
(A/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps(m['patches']))
