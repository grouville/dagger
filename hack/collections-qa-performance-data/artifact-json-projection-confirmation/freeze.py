#!/usr/bin/env python3
"""Freeze16-call confirmation source only; no engine or CLI invocation."""
from pathlib import Path
import hashlib,json
from lifecycle import x,LAB
P=Path(__file__).resolve().parent;OLD=P.parent/'runtime-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not(P/'frozen-runtime-inputs.json').exists()
f=json.loads((OLD/'frozen-runtime-inputs.json').read_text());rows=json.loads((OLD/'results-numeric.json').read_text());assert len(rows)==38 and all(r['correct']for r in rows)
initial=f['original_fixtures']['app'];assert x.fixture_hashes(OLD/'greetings')==initial
assert x.fixture_hashes(Path(f['original_fixture_roots']['app']))==initial
golden=OLD/'results-v1/07-00-baseline-primer-artifacts/stdout.private';assert sha(golden)==rows[7]['stdout_sha256']
paths=[P/'runtime.py',P/'lifecycle.py',P/'freeze.py',P/'frozen-engine-manifest.json',P/'frozen-cli-manifest.json',P/'frozen-sdk-inputs.json',P/'module-manifest.toml',OLD/'frozen-runtime-inputs.json',OLD/'summary-v1.json',OLD/'results-v1/lifecycle-restoration.json',OLD/'results-numeric.json',golden,Path(f['module_path']),LAB/'experiment.py',LAB/'navigation-generate.py',LAB/'withfile-cloud-warm.py',LAB/'lazy-core-runtime-v1/engines.json']
for name in initial:paths.extend((OLD/'greetings'/name,Path(f['original_fixture_roots']['app'])/name))
value={'source_sha256':{str(p):sha(p)for p in paths},'engine_manifest_sha256':sha(P/'frozen-engine-manifest.json'),'cli_manifest_sha256':sha(P/'frozen-cli-manifest.json'),'module_path':f['module_path'],'module_sha256':rows[7]['module_sha256'],'configured_dagger_toml_sha256':rows[7]['config_sha256'],'fixture_hashes':initial,'original_fixture_root':f['original_fixture_roots']['app'],'golden_path':str(golden),'local_cap':16,'cloud_calls':0}
(P/'frozen-runtime-inputs.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({'driver_sha256':sha(P/'runtime.py'),'lifecycle_sha256':sha(P/'lifecycle.py'),'frozen_inputs_sha256':sha(P/'frozen-runtime-inputs.json'),'calls':16,'executed':False}))
