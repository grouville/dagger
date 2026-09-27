"""Copy only reviewed build sources/manifests; never binaries or runtime data."""
from pathlib import Path
import hashlib,json,shutil
H=Path(__file__).resolve().parent;B=H/'engine-builds-v2';E=H/'engine-evidence-v2'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads((B/'build-recipe.json').read_text())
assert not E.exists();E.mkdir()
names={}
def copy(src,relative):
 src=Path(src);target=E/relative
 if target.suffix=='.go':
  names[str(target.relative_to(E))+'.txt']=str(target.relative_to(E));target=target.with_suffix('.go.txt')
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
for name in ('prepare-engines-v2.py','build-engines-v2.py','archive-engine-builds.py'):copy(H/name,name)
for name in ('build-recipe.json','build-results.json','runtime-builds.json','baseline-runtime-builds.json','candidate-runtime-builds.json'):
 copy(B/name,name)
for path,want in r['inputs'].items():
 assert sha(path)==want,path
 copy(path,Path('frozen-inputs')/Path(path).relative_to(B))
for name in ('build-recipe.json','build-results.json','baseline.build.private.log'):
 copy(H/'engine-builds-v1'/name,Path('setup-failure-v1')/(name.replace('.private','')))
copy(H/'engine-builds-v1/README.md','README.md')
(E/'archive-source-names.json').write_text(json.dumps(names,indent=2)+'\n')
summary={
 'scope':r['scope'],'source_head':r['source_head'],
 'matched_engine_builds':'Both exit0; identical clean VCS settings and pinned dependencies. Build durations are compiler/cache observations, not engine or CLI performance.',
 'setup_failure':'Initial v1 freeze omitted embedded Dang skill files. Baseline stopped before compilation; candidate was not attempted. v2 copies and hashes all declared embed inputs, without Go-source behavior changes.',
 'module_source_unchanged':True,'shared_dependency_unchanged':True,
 'runtime_calls':0,'cloud_calls':0,
 'excluded':'Engine binaries, raw profiles, inherited environment, credentials, source payloads from user commands.'
}
(E/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
files=[{'path':str(p.relative_to(E)),'sha256':sha(p)}for p in sorted(E.rglob('*'))if p.is_file()]
(E/'archive-allowlist.json').write_text(json.dumps({'files':files,'scope':summary['scope'],'raw_profiles_included':False,'binaries_included':False},indent=2)+'\n')
print(json.dumps({'allowlist':str(E/'archive-allowlist.json'),'sha256':sha(E/'archive-allowlist.json'),'files':len(files)}))
