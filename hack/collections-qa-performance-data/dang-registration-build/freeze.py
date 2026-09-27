from pathlib import Path
import difflib,hashlib,json,subprocess
P=Path(__file__).resolve().parent;ROOT=Path('/home/dagger/dag')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert (P/'helpers.baseline.go.txt').read_bytes()==(ROOT/'core/sdk/dang/v2/helpers.go').read_bytes()
production=['helpers.go','registration_metadata.go'];tests=['registration_metadata_test.go','registration_baseline_test.go','registration_metadata_bench_test.go']
replace={str(ROOT/'core/sdk/dang/v2'/f):str(P/'source'/f)for f in production+tests}
(P/'source-overlay.json').write_text(json.dumps({'Replace':{k:v for k,v in replace.items()if not k.endswith('_test.go')}},indent=2)+'\n')
(P/'test-overlay.json').write_text(json.dumps({'Replace':replace},indent=2)+'\n')
patch=''
for f in production+tests:
 q=ROOT/'core/sdk/dang/v2'/f;before=q.read_text()if q.exists()else'';after=(P/'source'/f).read_text()
 patch+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/core/sdk/dang/v2/'+f if q.exists()else'/dev/null',tofile='b/core/sdk/dang/v2/'+f))
(P/'prototype.patch').write_text(patch)
files=[P/'source'/f for f in production+tests]+list((P/'fixtures').iterdir())+[P/'prototype.patch',P/'test-overlay.json',P/'source-overlay.json',P/'helpers.baseline.go.txt',P/'freeze.py',P/'prepare.py',P/'gates.py',P/'README.md',P/'current-engine-plan.md']
m={'status':'source-only; formatted, not compiled or tested','source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'dependency':'current ordinary go.mod Dang v2.1.4; no historical engine.mod or parse-cache overlays','root_go_mod_sha256':sha(ROOT/'go.mod'),'root_go_sum_sha256':sha(ROOT/'go.sum'),'production_baseline_helpers_sha256':sha(ROOT/'core/sdk/dang/v2/helpers.go'),'files':{str(q.relative_to(P)):sha(q)for q in files}}
(P/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'manifest_sha256':sha(P/'manifest.json'),'patch_sha256':sha(P/'prototype.patch'),'source_head':m['source_head']}))
