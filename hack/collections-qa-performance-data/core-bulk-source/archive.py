"""Copy the explicit source/numeric allowlist; raw engine/CLI/telemetry payloads remain private."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'source-evidence-v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert json.loads((ROOT/'reviewed-v1/validation-v2/results.json').read_text())['all_passed']
assert not OUT.exists();OUT.mkdir()
files={
 'prototype.patch':'reviewed-v1/prototype.patch',
 'core_bulk_publication_test.go.txt':'reviewed-v1/core_bulk_publication_test.go',
 'core_bulk_publication_alias_test.go.txt':'reviewed-v1/core_bulk_publication_alias_test.go',
 'module_typedef_bulk.go.txt':'reviewed-v1/module_typedef_bulk.go',
 'validation-initial.json':'validation-v1/results.json',
 'validation-final.json':'reviewed-v1/validation-v2/results.json',
 'source-hashes.json':'reviewed-v1/hashes.json',
 'validation-final.py':'reviewed-v1/validate.py',
 'validation-initial.py':'validate.py',
 'benchmark.py':'benchmark.py',
 'benchmark-results.json':'benchmark-v1/results.json',
 'benchmark-summary.json':'benchmark-v1/summary.json',
 'build-engines.py':'build-engines.py',
 'build-recipe.json':'builds/build-recipe.json',
 'build-results.json':'builds/build-results.json',
 'runtime-builds.json':'builds/runtime-builds.json',
 'runtime.py':'runtime.py',
}
for name,source in files.items():(OUT/name).write_bytes((ROOT/source).read_bytes())
(OUT/'report.md').write_text('''The core metadata bulk-publication candidate remains isolated. Focused normal/race tests pass and fresh library construction improves291.62→238.92ms (18.1%), with14.2% fewer allocated bytes and14.7% fewer allocations. However, the separate ordinary retained-volume ABBA run shows only12.6ms improvement on the first API after restart and worse warm medians. It does not establish a warm UX gain, so the evidence does not justify applying it to production now.

The patch changes only the core object/interface metadata consumer after function IDs have already been collected. One private ordered bulk call replaces multiple intermediate immutable updates. The resolver applies the existing WithFunction implementation in order and publishes the final object through normal DagQL ownership/dependency paths. This removes intermediate publication and cache/recipe work. Local clone/scan complexity remains quadratic; no new metadata cache or public SDK binding is introduced.

The fail-first witness uses the unchanged consumer with the new private resolver present, avoiding an unrelated unknown-field failure. It fails only the ten-function object/interface work-count expectations; zero/one controls pass. Candidate normal/race tests pass, including core schema goldens, legacy/current JSON metadata parity, cross-session retention, ordered alias replacement, held receiver immutability and failure after a valid first update followed by an invalid typed ID.

The final reviewed source differs from the timed prototype only by test import grouping and added independent tests. Production source hashes are unchanged. Original source/test hashes and runtime binaries remain intact; this archive is a separate package. The first final-test attempt was blocked by a read-only Go build cache before tests ran; the authorized final run passed. Earlier build preflight rejected a documentation-only dirty file before compilation, subsequently explicitly allowlisted. Both attempts remain in local history.

Runtime method, raw numeric samples, counter/profile summaries and their limitations are in the separate runtime-evidence-v2 allowlist. It includes the rejected version-golden harness attempt (one successful command, exact version mismatch) and successful restoration of the original owned engine. No Cloud calls were made. The same experimental SDK/Dang/TypeScript stack was frozen in both engines at HEAD85b60f7; these are not unmodified-main performance figures.

The microbenchmark compiles each variant once, alternates AB/BA/AB with GOMAXPROCS4, and measures first core TypeDefs in a new cache/base while excluding schema setup and teardown. Its raw numbers and commands are preserved in the numeric files. The runtime is intentionally a retained-volume process-restart comparison, not a cold-volume benchmark.
''')
(OUT/'archive.py').write_bytes(Path(__file__).read_bytes())
metadata={'production_source_hashes':{n:sha(ROOT/'reviewed-v1'/n)for n in ['coremod.go','module.go','module_typedef_bulk.go']},
 'measured_source_hashes':{n:sha(ROOT/n)for n in ['coremod.go','module.go','module_typedef_bulk.go']},
 'final_validation_results_sha256':sha(ROOT/'reviewed-v1/validation-v2/results.json'),
 'initial_validation_attempt':{'classification':'environment build-cache permission failure before tests','results_sha256':sha(ROOT/'reviewed-v1/validation-v1/results.json')},
 'runtime_evidence_allowlist_sha256':sha(ROOT/'runtime-evidence-v2/allowlist.txt'),'status':'isolated; not applied; no demonstrated warm UX gain'}
assert metadata['production_source_hashes']==metadata['measured_source_hashes']
(OUT/'provenance.json').write_text(json.dumps(metadata,indent=2)+'\n')
names=sorted(p.name for p in OUT.iterdir())
(OUT/'checksums.json').write_text(json.dumps({n:sha(OUT/n)for n in names},indent=2)+'\n');names.append('checksums.json')
(OUT/'allowlist.txt').write_text('\n'.join(names)+'\n')
print(OUT/'allowlist.txt')
