#!/usr/bin/env python3
"""Freeze source and correctness evidence only; no Docker or Dagger calls."""
from pathlib import Path
import hashlib, json

HERE = Path(__file__).resolve().parent
ORDINARY = Path('/tmp/collections-perf/go-base-address-cold-v1/results-v1')
LAB = Path('/tmp/collections-perf')
GATE = LAB / 'go-base-address-retained-v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert not (HERE / 'frozen-inputs.json').exists()
manifest = LAB / 'go-base-address-v1/builds/runtime-builds.json'
build = json.loads(manifest.read_text())
assert build['engine']['sha256'] == '38711bd2b42e410f9fbf601d4260b47718e8169f7ff1d2caa29313adfba4569c'
assert build['cli']['sha256'] == 'd68580985d5eaa2350e7c4ec369d30ddfbb830ad8ea687d94228255b86ae76b8'
assert sha(build['engine']['path']) == build['engine']['sha256']
assert sha(build['cli']['path']) == build['cli']['sha256']
assert sha(build['recipe_path']) == build['recipe_sha256']
summary = json.loads((GATE / 'summary-v5.json').read_text())
restored = json.loads((GATE / 'results-v5/lifecycle-restoration.json').read_text())
assert summary['validated_cli_commands'] == restored['validated_commands'] == 9
assert summary['original_greetings_untouched'] and summary['synthetic_restored']
assert not restored['cleanup_error_types']
assert all(restored[key] for key in ('temporary_container_removed', 'original_engine_stopped', 'original_engine_binary_untouched', 'original_init_binary_untouched', 'retained_volume_preserved'))
inventory = LAB / 'engine-allocation-round2/withfile-v1/prepared.json'
original = json.loads(inventory.read_text())['input_sha256']
app = LAB / 'engine-allocation-round2/greetings'
assert all(sha(app / name) == wanted for name, wanted in original.items())
paths = {
    'engine_manifest': str(manifest),
    'fixture_inventory': str(inventory),
    'module_manifest': str(LAB / 'go-base-address-timing-v1/module-manifest.toml'),
    'control_module': str(LAB / 'warm-audit/module-before/go.dang'),
    'candidate_module': str(LAB / 'go-base-address-v1/module/go.dang'),
    'listing_golden': '/home/dagger/dag/hack/collections-qa-performance-data/expected-checks.txt',
}
ordinary = json.loads((ORDINARY / 'cleanup.json').read_text())
assert ordinary['validated_commands'] == 4 and ordinary['fixture_restored'] and ordinary['original_fixture_untouched']
assert len(json.loads((ORDINARY / 'volume-cleanup.json').read_text())['removed_owned_volumes']) == 4
files = [ORDINARY / 'cleanup.json', ORDINARY / 'volume-cleanup.json', ORDINARY / 'results.json', HERE / 'runtime.py', HERE / 'freeze.py', *map(Path, paths.values()), Path(build['recipe_path']), GATE / 'frozen-sdk-inputs.json', GATE / 'summary-v5.json', GATE / 'retained-result-v5.json', GATE / 'results-v5/lifecycle-restoration.json', *[app / name for name in original]]
result = {**paths, 'source_sha256': {str(path): sha(path) for path in files}, 'scope': 'Two profiled first-CLI fresh-volume check listings, control/candidate; no Cloud, primer or preparatory build/image pull; --profile enabled, excluded from ordinary stats.'}
(HERE / 'frozen-inputs.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'frozen_inputs_sha256': sha(HERE / 'frozen-inputs.json'), 'source_files': len(files), 'cli_cap': 2, 'cloud_calls': 0}))
