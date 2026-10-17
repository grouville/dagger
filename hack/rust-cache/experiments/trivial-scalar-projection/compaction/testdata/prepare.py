from pathlib import Path
import difflib
import hashlib
import json

root = Path(__file__).parent
work = Path('/tmp/dagger-compaction-ownership-only')
original = (work / 'dagql/cache_egraph.go').read_text()
(root / 'original-cache_egraph.go').write_text(original)
old = '''\t\tif oldDigests := c.eqClassToDigests[oldRoot]; len(oldDigests) > 0 {
\t\t\tnewDigests := make(map[string]struct{}, len(oldDigests))
\t\t\tfor dig := range oldDigests {
\t\t\t\tnewDigests[dig] = struct{}{}
\t\t\t\tnewEgraphDigestToClass[dig] = newRoot
\t\t\t}
\t\t\tnewEqClassToDigests[newRoot] = newDigests
\t\t}
\t\tif oldExtras := c.eqClassExtraDigests[oldRoot]; len(oldExtras) > 0 {
\t\t\tnewExtras := make(map[call.ExtraDigest]struct{}, len(oldExtras))
\t\t\tfor extra := range oldExtras {
\t\t\t\tnewExtras[extra] = struct{}{}
\t\t\t}
\t\t\tnewEqClassExtraDigests[newRoot] = newExtras
\t\t}'''
new = '''\t\tif oldDigests := c.eqClassToDigests[oldRoot]; len(oldDigests) > 0 {
\t\t\tfor dig := range oldDigests {
\t\t\t\tnewEgraphDigestToClass[dig] = newRoot
\t\t\t}
\t\t\tnewEqClassToDigests[newRoot] = oldDigests
\t\t}
\t\tif oldExtras := c.eqClassExtraDigests[oldRoot]; len(oldExtras) > 0 {
\t\t\tnewEqClassExtraDigests[newRoot] = oldExtras
\t\t}'''
assert original.count(old) == 1
shared = original.replace(old, new)
needle = 'newInputEqIDs := make([]eqClassID, 0, len(term.inputEqIDs))'
assert shared.count(needle) == 1
owned = shared.replace(needle, 'newInputEqIDs := term.inputEqIDs[:0]')
variants = {'baseline': original, 'digests': shared, 'owned': owned}
for name, source in variants.items():
    path = root / (name + '-cache_egraph.go')
    path.write_text(source)
    overlay = {'Replace': {str(work / 'dagql/cache_egraph.go'): str(path)}}
    for filename in ['compaction_ownership_test.go', 'compaction_ownership_bench_test.go']:
        overlay['Replace'][str(work / 'dagql' / filename)] = str(root / filename)
    (root / (name + '-overlay.json')).write_text(json.dumps(overlay, indent=2) + '\n')
    (root / (name + '.patch')).write_text(''.join(difflib.unified_diff(
        original.splitlines(True), source.splitlines(True), fromfile='a/dagql/cache_egraph.go', tofile='b/dagql/cache_egraph.go')))
(root / 'source-identities.json').write_text(json.dumps(dict(
    upstream_base='ff0b029a4d270a651b9a8c7286babc79089066e4',
    original_sha256=hashlib.sha256(original.encode()).hexdigest(),
    variants={name: hashlib.sha256(source.encode()).hexdigest() for name, source in variants.items()},
    previous_goal_turn='Progress: rejected two host-request approaches and aligned a publication stall with cache-index compaction.',
    goal_status='Active; complete Go collection listing and integrated Rust performance targets remain incomplete.'), indent=2) + '\n')
print('Prepared unchanged control, shared-digest variant, and shared-digest plus owned-input variant.', flush=True)
