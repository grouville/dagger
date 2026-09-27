"""Freeze the reviewed four-call local diagnostic inputs; no engine commands."""
from pathlib import Path
import hashlib
import json
import shutil

H = Path(__file__).resolve().parent
B = Path('/tmp/collections-perf/dang-admission-profile-v1/combined-build')
P = Path('/tmp/collections-perf/go-base-address-v1/builds')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (H / 'frozen-runtime-inputs.json').exists()
manifest = json.loads((B / 'runtime-builds.json').read_text())
assert manifest['engine']['sha256'] == '6a82b8b305b8415e42cc451e3ec5bd56208ab20eadc87b6a1a8de2a9c6685b4a'
assert manifest['behavior_engine_sha256'] == '38711bd2b42e410f9fbf601d4260b47718e8169f7ff1d2caa29313adfba4569c'
assert manifest['engine']['exit_code'] == 0
parent = json.loads((P / 'runtime-builds.json').read_text())
assert parent['engine']['sha256'] == manifest['behavior_engine_sha256']
# Add the independently recorded earlier ancestry key expected by the unchanged
# retained lifecycle, without modifying the actual diagnostic build manifest.
manifest['baseline_ancestry_engine_sha256'] = parent['baseline_ancestry_engine_sha256']
manifest['diagnostic_build_manifest_path'] = str(B / 'runtime-builds.json')
manifest['diagnostic_build_manifest_sha256'] = sha(B / 'runtime-builds.json')
(H / 'frozen-engine-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
candidate = Path('/tmp/collections-perf/go-base-address-v1/module/go.dang')
assert sha(candidate) == '0b12a6f3fe091f5896c19f642e2074593dceca554275b150a450e06732d640be'
golden = Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt')
sources = [H / 'runtime.py', H / 'lifecycle.py', H / 'freeze.py', H / 'module-manifest.toml', H / 'frozen-sdk-inputs.json', candidate, golden, B / 'runtime-builds.json', B / 'build-recipe.json', P / 'runtime-builds.json', Path('/tmp/collections-perf/engine-allocation-round2/experiment.py'), Path('/tmp/collections-perf/engine-allocation-round2/navigation-generate.py'), Path('/tmp/collections-perf/engine-allocation-round2/withfile-v1/prepared.json')]
frozen = {'engine_manifest_sha256': sha(H / 'frozen-engine-manifest.json'), 'source_sha256': {str(p): sha(p) for p in sources}, 'candidate_module': str(candidate), 'checks_golden': str(golden), 'local_cli_cap': 4, 'cloud_commands': 0}
(H / 'frozen-runtime-inputs.json').write_text(json.dumps(frozen, indent=2) + '\n')
print(json.dumps({'runtime_sha256': sha(H / 'runtime.py'), 'frozen_inputs_sha256': sha(H / 'frozen-runtime-inputs.json'), 'engine_sha256': manifest['engine']['sha256'], 'local_cli_cap': 4, 'cloud_commands': 0}))
