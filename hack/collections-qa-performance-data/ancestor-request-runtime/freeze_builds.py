"""Freeze reviewed binary provenance only; never starts Docker or a CLI."""
from pathlib import Path
import hashlib,json
here=Path(__file__).resolve().parent;src=Path('/tmp/collections-perf/ancestor-request-v1/builds');dest=here/'frozen-builds.json'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
assert not dest.exists();m=json.loads((src/'runtime-builds.json').read_text());r=json.loads((src/'build-recipe.json').read_text())
assert m['recipe_sha256']==sha(src/'build-recipe.json')
assert m['source_head']==r['source_head']=='85b60f7a0a16a27459ef571bc94bcf870c876dcc'
assert r['originals']['engine']['sha256']=='f864931c4dab6c53f7a1b552eace782eaf925e4dfa600bd5aa57a0099cb5189b'
assert m['variants']['baseline']['cli']['sha256']=='748700a2a203b2872461f5930c80d37a90c139c791929a7bc2b77bfbded9fe30'
assert m['wcprof_marker']=='filesync.syncParentDirs'
for v in m['variants'].values():
 for kind in ('cli','engine'):assert sha(v[kind]['path'])==v[kind]['sha256']
frozen=dict(m['variants'],source_head=m['source_head'],wcprof_marker=m['wcprof_marker'],original_baseline_engine_sha256=r['originals']['engine']['sha256'],parent_manifest_path=str(src/'runtime-builds.json'),parent_manifest_sha256=sha(src/'runtime-builds.json'),recipe_path=str(src/'build-recipe.json'),recipe_sha256=m['recipe_sha256'],comparison=m['comparison'])
dest.write_text(json.dumps(frozen,indent=2)+'\n');print(json.dumps({'frozen_manifest':str(dest),'sha256':sha(dest),'runtime_executed':False}))
