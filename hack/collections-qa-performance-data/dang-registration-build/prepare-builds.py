from pathlib import Path
import hashlib,json,subprocess
ROOT=Path('/home/dagger/dag');P=Path(__file__).resolve().parent;B=P/'builds'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((P/'manifest.json').read_text())
assert sha(ROOT/'go.mod')==m['root_go_mod_sha256']
assert sha(ROOT/'go.sum')==m['root_go_sum_sha256']
assert sha(ROOT/'core/sdk/dang/v2/helpers.go')==m['production_baseline_helpers_sha256']
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
assert head=='4f2ef6d70018b81f41d9b51140e76c82fe2fabab'
assert not subprocess.check_output(['git','diff','--name-only','HEAD','--','*.go','go.mod','go.sum'],cwd=ROOT,text=True).strip()
(B/'helpers.baseline.go').write_bytes((ROOT/'core/sdk/dang/v2/helpers.go').read_bytes())
(B/'helpers.snapshot.go').write_bytes((P/'source/helpers.go').read_bytes())
(B/'registration_metadata.go').write_bytes((P/'source/registration_metadata.go').read_bytes())
base={'Replace':{str(ROOT/'core/sdk/dang/v2/helpers.go'):str(B/'helpers.baseline.go')}}
cand={'Replace':{str(ROOT/'core/sdk/dang/v2/helpers.go'):str(B/'helpers.snapshot.go'),str(ROOT/'core/sdk/dang/v2/registration_metadata.go'):str(B/'registration_metadata.go')}}
for n,v in [('baseline-overlay.json',base),('snapshot-overlay.json',cand)]: (B/n).write_text(json.dumps(v,indent=2)+'\n')
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
image='sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
cli=Path('/tmp/collections-perf/shared-client-transport-v1/prototype-v2/builds/dagger-original')
common={'CGO_ENABLED':'0','GOOS':'linux','GOARCH':'amd64','GOAMD64':'v1','GOMAXPROCS':'4','GOPROXY':'off','GOTOOLCHAIN':'local'}
commands={n:[go,'build','-mod=readonly','-buildvcs=true','-overlay='+str(B/(n+'-overlay.json')),'-o',str(B/('engine-'+n)),'./cmd/engine']for n in ('baseline','snapshot')}
inputs=[ROOT/'internal/version/VERSION',ROOT/'internal/version/version.go',ROOT/'go.mod',ROOT/'go.sum',ROOT/'sdk/go/go.mod',ROOT/'sdk/go/go.sum',ROOT/'engine/distconsts/go.mod',ROOT/'engine/distconsts/go.sum',P/'manifest.json',P/'source-overlay.json',P/'validation-v2/validation.json',P/'micro-summary.json',P/'build.py',P/'prepare-builds.py']+list(B.glob('*.go'))+list(B.glob('*-overlay.json'))
recipe={'source_head':head,'expected_core_version':'v'+(ROOT/'internal/version/VERSION').read_text().strip().removeprefix('v')+'+'+head[:8],'working_tree_must_have_no_tracked_changes':True,'toolchain':go,'environment':common,'commands':commands,'source_scope':'Current production branch and ordinary go.mod in both; only candidate adds the registration metadata snapshot. No historical source/dependency overlays.','cli':{'path':str(cli),'sha256':sha(cli)},'common_image':image,'common_sdk_inputs':{'path':'/tmp/collections-perf/go-base-address-retained-v1/frozen-sdk-inputs.json','sha256':sha(Path('/tmp/collections-perf/go-base-address-retained-v1/frozen-sdk-inputs.json'))},'common_go_module':{'path':str(Path('/tmp/collections-perf/go-base-address-v1/module/go.dang')),'sha256':sha(Path('/tmp/collections-perf/go-base-address-v1/module/go.dang'))},'inputs':{str(q):sha(q)for q in inputs if q.exists()}}
(B/'build-recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
print(json.dumps({'recipe_sha256':sha(B/'build-recipe.json'),'current_source_head':head,'commands_prepared':2,'executed':False}))
