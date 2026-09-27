#!/usr/bin/env python3
"""Freeze source and completed matched builds only; no engine/CLI/container call.

Run after the earlier clone matrix restores its shared fixtures. Binary and
artifact hashing is preparation outside all timed samples.
"""
from pathlib import Path
import hashlib, json, subprocess
HERE=Path(__file__).resolve().parent
BUILD=Path('/tmp/collections-perf/dang-registration-snapshot-v1/builds')
LAB=Path('/tmp/collections-perf/engine-allocation-round2')
APP=Path('/tmp/collections-perf/dang-admission-runtime-v1/greetings-v1')
NATIVE=LAB/'native'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fixture(root):return{str(p.relative_to(root)):sha(p)for p in sorted(root.rglob('*'))if p.is_file()and not any(part in ('.git','node_modules')for part in p.relative_to(root).parts)}
assert not(HERE/'frozen-runtime-inputs.json').exists()
runtime=json.loads((BUILD/'runtime-builds.json').read_text());recipe=json.loads((BUILD/'build-recipe.json').read_text())
assert runtime['recipe_sha256']==sha(BUILD/'build-recipe.json')
assert runtime['source_head']=='4f2ef6d70018b81f41d9b51140e76c82fe2fabab'
assert runtime['source_head']==recipe['source_head']
assert runtime['cli']['sha256']=='d68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8'
assert runtime['image']=='sha256:b00e366e582ab98f0e4a7907163f338b6be3bfa13b10f3ad6bac3d699cd25a07'
assert runtime['common_go_module']['sha256']=='0b12a6f3fe091f5896c19f642e2074593dceca554275b150a450e06732d640be'
assert runtime['common_sdk_inputs']['sha256']==sha(HERE/'frozen-sdk-inputs.json')
assert sha(runtime['cli']['path'])==runtime['cli']['sha256']
assert sha(runtime['common_go_module']['path'])==runtime['common_go_module']['sha256']
for path,want in json.loads((HERE/'frozen-sdk-inputs.json').read_text())['sdk_blobs'].items():assert sha(path)==want
# The current production pair has ordinary module dependencies and only two
# candidate source replacements. No historical sdk/core/telemetry overlay leaks.
base=json.loads((BUILD/'baseline-overlay.json').read_text())['Replace']
candidate=json.loads((BUILD/'snapshot-overlay.json').read_text())['Replace']
assert set(base)=={'/home/dagger/dag/core/sdk/dang/v2/helpers.go'}
assert set(candidate)==set(base)|{'/home/dagger/dag/core/sdk/dang/v2/registration_metadata.go'}
assert '-modfile'not in ' '.join(recipe['commands']['baseline']+recipe['commands']['snapshot'])
engine_manifests={};pending_manifests={}
for variant,key in [('baseline','baseline'),('candidate','snapshot')]:
 engine=runtime['variants'][key]
 assert engine['vcs_revision']==runtime['source_head']and engine['vcs_modified']is False
 assert sha(engine['path'])==engine['sha256']
 manifest={'source_head':runtime['source_head'],'scope':runtime['scope'],'engine':{'path':engine['path'],'sha256':engine['sha256'],'exit_code':0},'expected_core_version':runtime['expected_core_version'],'recipe_path':str(BUILD/'build-recipe.json'),'recipe_sha256':runtime['recipe_sha256']}
 path=HERE/('frozen-'+variant+'-engine-manifest.json');assert not path.exists();body=(json.dumps(manifest,indent=2)+'\n').encode();pending_manifests[path]=body;engine_manifests[variant]=hashlib.sha256(body).hexdigest()
fixtures={'app':fixture(APP),'native':fixture(NATIVE)}
assert fixtures['app']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
assert fixtures['app']==fixture(LAB/'greetings')
assert not(APP/'.dagger/perf-go').exists()
assert subprocess.check_output(['git','-C',str(APP),'rev-parse','--show-toplevel'],text=True).strip()==str(APP)
assert subprocess.check_output(['git','-C',str(NATIVE),'rev-parse','--show-toplevel'],text=True).strip()==str(NATIVE)
golden=Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt')
paths={HERE/n for n in ['runtime.py','lifecycle.py','freeze.py','source-ancestry.json','module-manifest.toml','frozen-sdk-inputs.json']}
paths|={BUILD/'runtime-builds.json',BUILD/'build-recipe.json',BUILD/'baseline-overlay.json',BUILD/'snapshot-overlay.json',Path(runtime['common_go_module']['path']),golden,LAB/'withfile-v1/prepared.json',LAB/'lazy-core-runtime-v1/engines.json',LAB/'experiment.py',LAB/'navigation-generate.py',LAB/'withfile-cloud-warm.py'}
# The reviewed navigation module's own numeric helper is dynamically imported.
nav=(LAB/'navigation-generate.py').read_text()
assert "warm.py"in nav
assert all(p.is_file()for p in paths)
frozen={'source_head':runtime['source_head'],'engine_scope':runtime['scope'],'engine_manifest_sha256':engine_manifests,'source_sha256':{str(p):sha(p)for p in sorted(paths)},'fixtures':fixtures,'module_path':runtime['common_go_module']['path'],'checks_golden':str(golden),'local_cli_cap':36,'cloud_commands':0,'scope':'Current branch with ordinary dependencies; registration snapshot is sole engine delta; retained-volume warm/control/profile matrix.'}
for path,body in pending_manifests.items():path.write_bytes(body)
(HERE/'frozen-runtime-inputs.json').write_text(json.dumps(frozen,indent=2)+'\n')
print(json.dumps({'driver_sha256':sha(HERE/'runtime.py'),'lifecycle_sha256':sha(HERE/'lifecycle.py'),'frozen_inputs_sha256':sha(HERE/'frozen-runtime-inputs.json'),'local_cli_cap':36,'executed_commands':0}))
