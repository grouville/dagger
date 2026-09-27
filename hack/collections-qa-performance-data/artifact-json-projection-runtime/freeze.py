#!/usr/bin/env python3
"""Freeze reviewed runtime inputs; no engine/CLI calls."""
from pathlib import Path
import hashlib,json,shutil
from lifecycle import x,LAB
P=Path(__file__).resolve().parent;B=P.parent/'builds-v1';G=Path('/tmp/collections-perf/go-base-address-retained-v1')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not(P/'frozen-runtime-inputs.json').exists()
manifest=json.loads((B/'runtime-builds.json').read_text())
assert all(manifest[v]['exit_code']==0 and sha(manifest[v]['path'])==manifest[v]['sha256']for v in ('baseline','candidate'))
assert manifest['parent_cli']['sha256']=='d68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8'
assert sha(manifest['recipe_path'])==manifest['recipe_sha256']
shutil.copyfile(B/'runtime-builds.json',P/'frozen-cli-manifest.json')
summary=json.loads((G/'summary-v5.json').read_text());restored=json.loads((G/'results-v5/lifecycle-restoration.json').read_text())
assert summary['validated_cli_commands']==9 and restored['validated_commands']==9 and not restored['cleanup_error_types']
module=Path('/tmp/collections-perf/go-base-address-v1/module/go.dang');assert sha(module)=='0b12a6f3fe091f5896c19f642e2074593dceca554275b150a450e06732d640be'
roots={'app':LAB/'greetings','native':LAB/'native'};fixtures={k:x.fixture_hashes(p)for k,p in roots.items()}
assert fixtures['app']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
paths=[P/'runtime.py',P/'lifecycle.py',P/'freeze.py',P/'module-manifest.toml',P/'frozen-engine-manifest.json',P/'frozen-sdk-inputs.json',P/'frozen-cli-manifest.json',Path(manifest['recipe_path']),B/'build-results.json',G/'summary-v5.json',G/'results-v5/lifecycle-restoration.json',module,LAB/'experiment.py',LAB/'navigation-generate.py',LAB/'withfile-cloud-warm.py',LAB/'lazy-core-runtime-v1/engines.json',LAB/'withfile-v1/prepared.json',Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt')]
for key,root in roots.items():paths.extend(root/name for name in fixtures[key])
frozen={'source_sha256':{str(p):sha(p)for p in paths},'engine_manifest_sha256':sha(P/'frozen-engine-manifest.json'),'cli_manifest_sha256':sha(P/'frozen-cli-manifest.json'),'module_path':str(module),'expected_checks_path':'/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt','original_fixture_roots':{k:str(p)for k,p in roots.items()},'original_fixtures':fixtures,'local_cli_cap':38,'cloud_calls':0}
(P/'frozen-runtime-inputs.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps({'driver_sha256':sha(P/'runtime.py'),'lifecycle_sha256':sha(P/'lifecycle.py'),'freeze_sha256':sha(P/'freeze.py'),'frozen_inputs_sha256':sha(P/'frozen-runtime-inputs.json'),'engine_manifest_sha256':frozen['engine_manifest_sha256'],'cli_manifest_sha256':frozen['cli_manifest_sha256'],'executed':False}))
