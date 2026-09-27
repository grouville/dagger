import hashlib,json,os,pathlib,shutil,subprocess
R=pathlib.Path('/home/dagger/dag');P=pathlib.Path('/tmp/collections-perf/ancestor-request-v1');B=P/'builds';I=B/'inputs'
B.mkdir(exist_ok=True);I.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();assert head=='85b60f7a0a16a27459ef571bc94bcf870c876dcc'
old_engine=pathlib.Path('/tmp/collections-perf/sdk-edit-audit/core-bulk-publication-v1/builds')
old_cli=pathlib.Path('/tmp/collections-perf/cli-log-overlap-v3/backport-v016/builds')
assert sha(old_engine/'engine-baseline')=='f864931c4dab6c53f7a1b552eace782eaf925e4dfa600bd5aa57a0099cb5189b'
assert sha(old_cli/'dagger-baseline')=='748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30'
base=json.loads((old_engine/'baseline-overlay.json').read_text())['Replace'];frozen={}
for i,(key,src) in enumerate(base.items()):
 dst=I/f'base-{i:02}-{pathlib.Path(src).name}';shutil.copy2(src,dst);frozen[key]=str(dst)
explicit=json.loads((P/'source-overlay.json').read_text())['Replace'];candidate={}
for i,(key,src) in enumerate(explicit.items()):
 dst=I/f'parent-{i:02}-{pathlib.Path(src).name}';shutil.copy2(src,dst);candidate[key]=str(dst)
marker=I/'baseline-filesyncer-profile.go';shutil.copy2(P/'baseline-filesyncer-profile.go',marker)
base_marker=frozen|{str(R/'engine/filesync/filesyncer.go'):str(marker)}
full=frozen|candidate
for name,overlay in [('engine-baseline',base_marker),('engine-candidate',full),('cli-candidate',candidate)]:
 (B/(name+'-overlay.json')).write_text(json.dumps({'Replace':overlay},indent=2)+'\n')
for stem,src in [('engine',old_engine),('cli',old_cli)]:
 for suffix in ['mod','sum']:shutil.copy2(src/(stem+'.'+suffix),B/(stem+'.'+suffix))
go='/home/dagger/go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.6.linux-amd64/bin/go'
env={'CGO_ENABLED':'0','GOOS':'linux','GOARCH':'amd64','GOAMD64':'v1','GOMAXPROCS':'4','GOPROXY':'off','GOTOOLCHAIN':'local'}
commands={}
for name,stem,target in [('engine-baseline','engine','./cmd/engine'),('engine-candidate','engine','./cmd/engine'),('cli-candidate','cli','./cmd/dagger')]:
 commands[name]=[go,'build','-mod=readonly','-modfile='+str(B/(stem+'.mod')),'-buildvcs=true','-overlay='+str(B/(name+'-overlay.json')),'-o',str(B/name),target]
inputs={str(p):sha(p) for p in list(I.iterdir())+list(B.glob('*.json'))+list(B.glob('*.mod'))+list(B.glob('*.sum'))}
recipe={'source_head':head,'source_tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=R,text=True).strip(),'tracked_changes':subprocess.check_output(['git','diff','--name-only'],cwd=R,text=True).splitlines(),'source_parent_recipes':{str(old_engine/'build-recipe.json'):sha(old_engine/'build-recipe.json'),str(old_cli/'build-recipe.json'):sha(old_cli/'build-recipe.json')},'originals':{'engine':{'path':str(old_engine/'engine-baseline'),'sha256':sha(old_engine/'engine-baseline')},'cli':{'path':str(old_cli/'dagger-baseline'),'sha256':sha(old_cli/'dagger-baseline')}},'environment':env,'commands':commands,'inputs':inputs,'status':'prepared_not_built','comparison':'Only explicit parent metadata request differs. Both engines contain the same fixed filesync.syncParentDirs wcprof marker, inactive without profiling. Baseline CLI is the retained byte-identical748 binary. No core bulk/span/log changes; same frozen f864 SDK/Dang stack.'}
(B/'build-recipe.json').write_text(json.dumps(recipe,indent=2)+'\n')
