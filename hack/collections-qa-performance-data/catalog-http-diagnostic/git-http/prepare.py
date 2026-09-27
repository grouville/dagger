from pathlib import Path
import json,hashlib,subprocess,shutil,difflib
D=Path(__file__).resolve().parent;B=D/'builds';R=Path('/home/dagger/dag');P=Path('/tmp/collections-perf/ancestor-request-v1/builds')
B.mkdir(exist_ok=True);I=B/'inputs';I.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
parent=json.loads((P/'build-recipe.json').read_text());orig=json.loads((P/'runtime-builds.json').read_text());parentoverlay=json.loads((P/'engine-candidate-overlay.json').read_text())['Replace']
# Preserve every pre-existing frozen candidate overlay source and pin it.
replace={}
for i,(target,source) in enumerate(parentoverlay.items()):
 assert sha(source)==parent['inputs'][source],source
 dest=I/f'{i:02d}-{Path(source).name}';shutil.copyfile(source,dest);replace[target]=str(dest)
# The two current source files have not changed since the retained parent build.
git=R/'core/schema/git_visibility.go'
assert subprocess.check_output(['git','show',parent['source_head']+':core/schema/git_visibility.go'],cwd=R)==git.read_bytes()
for name in ('git_visibility.go','git_advertisement_http_audit.go'):
 dest=I/name;shutil.copyfile(D/name,dest);replace[str(R/'core/schema'/name)]=str(dest)
# Fixed-label instrumentation only, applied to the EXACT frozen experimental
# modulesource.go (retains its SDK/static-metadata behavior and dependency pins).
target=str(R/'core/schema/modulesource.go');p=Path(replace[target]);s=p.read_text()
a='''\t\tif err := s.loadModuleSourceContext(ctx, src); err != nil {
			return fmt.Errorf("load module source context: %w", err)
		}
		if src.SDK != nil {
			loaded, err := sdk.NewLoader().SDKForModule(ctx, query, src.SDK, src)'''
b='''\t\tcontextCtx, contextOp := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "moduleSource.loadContext", wcprof.OpOpts{})
		contextErr := s.loadModuleSourceContext(contextCtx, src)
		contextOp.EndErr(contextErr)
		if contextErr != nil {
			return fmt.Errorf("load module source context: %w", contextErr)
		}
		if src.SDK != nil {
			sdkCtx, sdkOp := wcprof.BeginOp(ctx, wcprof.OpKindInternal, "moduleSource.loadSDK", wcprof.OpOpts{})
			loaded, err := sdk.NewLoader().SDKForModule(sdkCtx, query, src.SDK, src)
			sdkOp.EndErr(err)'''
assert s.count(a)==1
assert '"github.com/dagger/dagger/engine/wcprof"'in s
candidate=s.replace(a,b)
p.write_text(candidate)
(D/'context-sdk-instrumentation.patch').write_text(''.join(difflib.unified_diff(s.splitlines(True),candidate.splitlines(True),fromfile='a/core/schema/modulesource.go',tofile='b/core/schema/modulesource.go')))
for name in ('engine.mod','engine.sum'):shutil.copyfile(P/name,B/name)
write(B/'engine-overlay.json',{'Replace':replace})
testrepl=replace|{str(R/'core/schema/git_advertisement_http_audit_test.go'):str(D/'git_advertisement_http_audit_test.go')};write(B/'test-overlay.json',{'Replace':testrepl})
go=parent['commands']['engine-candidate'][0];env=parent['environment']
common=[go,'test','-mod=readonly',f'-modfile={B}/engine.mod',f'-overlay={B}/test-overlay.json','-count=1','-run','^(TestGitAdvertisementHTTPAudit.*|TestPublicRemoteAdvertisement|TestRemoteAdvertisementDoesNotInventSymbolicHEAD)$','./core/schema']
recipe={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),'frozen_parent_source_head':parent['source_head'],'parent_recipe_sha256':sha(P/'build-recipe.json'),'parent_runtime_builds_sha256':sha(P/'runtime-builds.json'),'parent_engine':orig['variants']['candidate']['engine'],'cli':orig['variants']['candidate']['cli'],'environment':env,'test_environments':{'normal':env,'race':env|{'CGO_ENABLED':'1'}},'test_commands':{'normal':common,'race':common[:2]+['-race']+common[2:]},'build_command':[go,'build','-mod=readonly',f'-modfile={B}/engine.mod','-buildvcs=true',f'-overlay={B}/engine-overlay.json','-o',str(B/'engine-diagnostic'),'./cmd/engine'],'inputs':{str(p):sha(p)for p in [*map(Path,replace.values()),D/'git_advertisement_http_audit_test.go',B/'engine.mod',B/'engine.sum',B/'engine-overlay.json',B/'test-overlay.json']},'scope':'Frozen parent candidate stack; Git HTTP/validation/materialization and source-context/SDK load wcprof instrumentation only. Existing transport/cache/SDK/call ordering unchanged. No behavior optimization.','no_cloud':True}
write(B/'recipe.json',recipe)
print(json.dumps({'recipe':str(B/'recipe.json'),'sha256':sha(B/'recipe.json'),'source_files':len(replace),'normal_test_command':common}))
