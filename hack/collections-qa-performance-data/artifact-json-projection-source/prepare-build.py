#!/usr/bin/env python3
"""Freeze matched CLI recipes; no Go build or engine invocation."""
from pathlib import Path
import hashlib,json,subprocess,shutil
P=Path(__file__).resolve().parent;R=Path('/home/dagger/dag');B=P/'builds-v1'
OLD=Path('/tmp/collections-perf/shared-client-transport-v1/prototype-v2/builds')
REF='0d1c32e29f2f31cdb95f0b5f17f7daed7305bc87'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=R)
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
assert not B.exists();(B/'inputs').mkdir(parents=True)
prior=json.loads((OLD/'build-recipe.json').read_text());assert prior['source_head']==REF
assert sha(OLD/'dagger-original')=='d68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8'
changed=git('diff','--no-renames','--name-only',REF,'--',':!hack/**').decode().splitlines()
assert all(name.endswith('.go')for name in changed),'unexpected non-Go source delta requires review'
replace={};guards={};provenance={}
for name in changed:
 path=R/name;guards[str(path)]=sha(path)if path.exists()else None
 exists=subprocess.run(['git','cat-file','-e',REF+':'+name],cwd=R,stderr=subprocess.DEVNULL).returncode==0
 if exists:
  target=B/'inputs'/'historical'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(git('show',REF+':'+name));replace[str(path)]=str(target)
 else:replace[str(path)]=''
 provenance[name]={'current_sha256':guards[str(path)],'historical_sha256':sha(replace[str(path)])if replace[str(path)]else None}
# Preserve the original d685 effective overlay, not held shared-transport variants.
for name,source in json.loads((OLD/'original-overlay.json').read_text())['Replace'].items():
 target=B/'inputs'/('original-'+Path(name).relative_to(R).as_posix().replace('/','-'));shutil.copyfile(source,target);replace[name]=str(target)
for name in ('cli.mod','cli.sum'):shutil.copyfile(OLD/name,B/name)
# The modfile's absolute local replacement paths stay exactly as used by d685.
external={}
for root in (OLD/'inputs/otel-go-pinned',Path('/tmp/collections-perf/cli-log-overlap-v3/backport-v016/builds/inputs/sdk-log-v016')):
 for path in sorted(root.rglob('*')):
  if path.is_file():external[str(path)]=sha(path)
source=json.loads((P/'source-overlay.json').read_text())['Replace'];baseline=dict(replace);candidate=dict(replace)
for name,path in source.items():
 target=B/'inputs'/'projection'/Path(name).relative_to(R);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);candidate[name]=str(target)
 # Both original readers and generated SDK already equal their historical sources.
 guards.setdefault(name,sha(name)if Path(name).exists()else None)
 if name.endswith('/internal/cmd/dagger/artifacts.go'):assert Path(name).read_bytes()==git('show',REF+':internal/cmd/dagger/artifacts.go')
for name,mapping in [('baseline',baseline),('candidate',candidate)]:save(B/(name+'-overlay.json'),{'Replace':mapping})
files={str(path):sha(path)for path in B.rglob('*')if path.is_file()}
validation=P/'validation-v2/results.json';assert all(x['expected_outcome']for x in json.loads(validation.read_text())['steps'])
recipe={'historical_effective_source':REF,'current_build_vcs_head':git('rev-parse','HEAD').decode().strip(),'parent_cli':{'path':str(OLD/'dagger-original'),'sha256':sha(OLD/'dagger-original')},'parent_recipe_sha256':sha(OLD/'build-recipe.json'),'source_guards':guards,'post_historical_source_differences':provenance,'inputs':files,'external_local_dependencies':external,'validation_sha256':sha(validation),'validation_path':str(validation),'toolchain':prior['commands']['original'][0],'environment':prior['environment'],'commands':{},'scope':'Both freshly built CLIs restore d685 effective source and retain its exact dependency pins; they have the same current VCS stamp. Candidate differs only in the two direct JSON projection production files. No engine, transport, init, caching or telemetry changes.','runtime_calls':0,'cloud_calls':0}
for name in ('baseline','candidate'):recipe['commands'][name]=[recipe['toolchain'],'build','-mod=readonly','-modfile='+str(B/'cli.mod'),'-buildvcs=true','-overlay='+str(B/(name+'-overlay.json')),'-o',str(B/('dagger-'+name)),'./cmd/dagger']
save(B/'build-recipe.json',recipe)
print(json.dumps({'recipe':str(B/'build-recipe.json'),'sha256':sha(B/'build-recipe.json'),'historical_source_files':len(changed),'candidate_delta':list(source),'executed':False}))
