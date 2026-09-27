#!/usr/bin/env python3
"""Freeze reviewed build/source inputs; no Docker, Dagger or network calls."""
from pathlib import Path
import argparse,hashlib,json
HERE=Path(__file__).resolve().parent
P=argparse.ArgumentParser();P.add_argument('--engine-manifest',type=Path,required=True);P.add_argument('--engine-manifest-sha256',required=True);a=P.parse_args()
def sha(f):return hashlib.sha256(Path(f).read_bytes()).hexdigest()
assert not (HERE/'frozen-runtime-inputs.json').exists()
assert sha(a.engine_manifest)==a.engine_manifest_sha256
manifest=json.loads(a.engine_manifest.read_text())
assert manifest['baseline_ancestry_engine_sha256']=='ec6a2d88ca54b1c12fc81c7381538e23d100fece04d703daac0b17dcf3d3ebc1'
assert manifest['engine']['exit_code']==0 and sha(manifest['engine']['path'])==manifest['engine']['sha256']
assert sha(manifest['recipe_path'])==manifest['recipe_sha256']
assert manifest['expected_core_version'].startswith('v1.0.0-beta.15+')
(HERE/'frozen-engine-manifest.json').write_bytes(a.engine_manifest.read_bytes())
original=Path('/tmp/collections-perf/warm-audit/module-before/go.dang')
candidate=Path('/tmp/collections-perf/go-base-address-v1/module/go.dang')
lab=Path('/tmp/collections-perf/engine-allocation-round2')
inventory=lab/'withfile-v1/prepared.json'
app=lab/'greetings'
expected=json.loads(inventory.read_text())['input_sha256']
for name,want in expected.items():assert sha(app/name)==want
files=[HERE/n for n in ('runtime.py','lifecycle.py','probe.py','prepare.py','freeze.py','frozen-sdk-inputs.json')]+[original,candidate,inventory,lab/'lazy-core-runtime-v1/engines.json',
 Path('/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt'),
 Path('/tmp/collections-perf/cli-key-scaling/ux-local-production-v2/warmup/filtered-checks-candidate/stdout.txt'),
 *[lab/n for n in ('experiment.py','navigation-generate.py','withfile-cloud-warm.py')],
 *[app/name for name in expected],*[f for f in (HERE/'fixture').rglob('*')if f.is_file()]]
result={'engine_manifest_sha256':sha(HERE/'frozen-engine-manifest.json'),'source_sha256':{str(f):sha(f)for f in files},'original_module':str(original),'candidate_module':str(candidate),'local_cli_cap':9,'retained_session_rpc_cap':10,'cloud_commands':0}
(HERE/'frozen-runtime-inputs.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'frozen_inputs_sha256':sha(HERE/'frozen-runtime-inputs.json'),'engine_sha256':manifest['engine']['sha256'],'local_cli_cap':9,'retained_session_rpc_cap':10,'cloud_commands':0}))
