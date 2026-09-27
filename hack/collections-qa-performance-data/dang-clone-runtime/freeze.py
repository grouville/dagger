"""Freeze source/binary/fixture inputs only; no engine or CLI calls."""
from pathlib import Path
import hashlib,json,shutil
from lifecycle import x,LAB,CLI,CLI_SHA,INPUTS_SHA
H=Path(__file__).resolve().parent;B=Path('/tmp/collections-perf/dang-clone-inplace-v1/engine-builds-v2')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not(H/'frozen-runtime-inputs.json').exists()
manifest=json.loads((B/'runtime-builds.json').read_text())
assert sha(manifest['recipe_path'])==manifest['recipe_sha256']
assert sha(CLI)==manifest['cli']['sha256']==CLI_SHA
engine_hashes={}
for variant in ('baseline','candidate'):
 v=manifest['variants'][variant];source=Path(v['manifest_path'])
 assert sha(source)==v['manifest_sha256']
 entry=json.loads(source.read_text());assert entry['engine']['exit_code']==0
 assert sha(entry['engine']['path'])==entry['engine']['sha256']
 assert entry['effective_parent_engine_sha256']=='6a82b8b305b8415e42cc451e3ec5bd56208ab20eadc87b6a1a8de2a9c6685b4a'
 assert entry['variant']==variant and entry['cloud_commands']==entry['runtime_commands']==0
 assert entry['expected_core_version']==v['expected_core_version']=='v1.0.0-beta.15+4f2ef6d7'
 shutil.copyfile(source,H/f'frozen-{variant}-engine-manifest.json')
 engine_hashes[variant]=sha(H/f'frozen-{variant}-engine-manifest.json')
assert sha(H/'frozen-sdk-inputs.json')==INPUTS_SHA
sdk=json.loads((H/'frozen-sdk-inputs.json').read_text())
for path,want in sdk['sdk_blobs'].items():assert sha(path)==want
module=Path('/tmp/collections-perf/go-base-address-v1/module/go.dang')
assert sha(module)=='0b12a6f3fe091f5896c19f642e2074593dceca554275b150a450e06732d640be'
roots={'app':Path('/tmp/collections-perf/dang-admission-runtime-v1/greetings-v1'),'native':LAB/'native'}
fixtures={k:x.fixture_hashes(p)for k,p in roots.items()}
assert fixtures['app']==json.loads((LAB/'withfile-v1/prepared.json').read_text())['input_sha256']
assert x.fixture_hashes(LAB/'greetings')==fixtures['app']
paths=[H/'runtime.py',H/'lifecycle.py',H/'freeze.py',H/'module-manifest.toml',H/'frozen-sdk-inputs.json',B/'runtime-builds.json',Path(manifest['recipe_path']),B/'build-results.json',module,LAB/'experiment.py',LAB/'navigation-generate.py',LAB/'withfile-cloud-warm.py',LAB/'lazy-core-runtime-v1/engines.json',LAB/'withfile-v1/prepared.json',Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt')]
for k,root in roots.items():paths.extend(root/name for name in fixtures[k])
x={'source_sha256':{str(p):sha(p)for p in paths},'engine_manifest_sha256':engine_hashes,'module_path':str(module),'checks_golden':'/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt','fixtures':fixtures,'fixture_roots':{k:str(p)for k,p in roots.items()},'local_cli_cap':36,'cloud_commands':0,'engine_build_manifest_sha256':sha(B/'runtime-builds.json'),'scope':'Same existing app path, 0b12 baseAddress implementation, CLI and ordinary init. Only clone differs; fixed profiling present both arms.'}
(H/'frozen-runtime-inputs.json').write_text(json.dumps(x,indent=2)+'\n')
print(json.dumps({'executed_runtime':False,'driver_sha256':sha(H/'runtime.py'),'lifecycle_sha256':sha(H/'lifecycle.py'),'frozen_runtime_inputs_sha256':sha(H/'frozen-runtime-inputs.json'),'engine_manifest_sha256':engine_hashes},indent=2))
