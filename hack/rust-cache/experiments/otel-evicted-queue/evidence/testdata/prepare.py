from pathlib import Path
import difflib
import hashlib
import json
import shutil

root = Path(__file__).parent
sdk = Path('/home/dagger/go/pkg/mod/go.opentelemetry.io/otel/sdk@v1.43.0/trace')
source = (sdk / 'evictedqueue.go').read_text()
local_sdk = root / 'sdk'
if not local_sdk.exists():
    shutil.copytree(sdk.parent, local_sdk)
module = root.parent / 'span-resource-batches/engine.go.mod'
(root / 'engine.go.mod').write_text(module.read_text() + '\nreplace go.opentelemetry.io/otel/sdk => ' + str(local_sdk) + '\n')
shutil.copyfile(module.with_suffix('.sum'), root / 'engine.go.sum')
changed = source.replace(
    '\tqueue          []T\n',
    '\tqueue          []T\n\thead           int\n',
)
old = '''		// Drop first-in while avoiding allocating more capacity to eq.queue.
		copy(eq.queue[:eq.capacity-1], eq.queue[1:])
		eq.queue = eq.queue[:eq.capacity-1]
		eq.droppedCount++
		eq.logDropped()
'''
new = '''		// Replace the oldest value without shifting the retained values.
		eq.queue[eq.head] = value
		eq.head++
		if eq.head == len(eq.queue) {
			eq.head = 0
		}
		eq.droppedCount++
		eq.logDropped()
		return
'''
assert changed.count(old) == 1
changed = changed.replace(old, new)
old = '''	return slices.Clone(eq.queue)
'''
new = '''	if eq.head == 0 {
		return slices.Clone(eq.queue)
	}
	queue := make([]T, len(eq.queue))
	n := copy(queue, eq.queue[eq.head:])
	copy(queue[n:], eq.queue[:eq.head])
	return queue
'''
assert changed.count(old) == 1
changed = changed.replace(old, new)
(root / 'evictedqueue-before.go').write_text(source)
(root / 'evictedqueue-after.go').write_text(changed)
(root / 'standalone.patch').write_text(''.join(difflib.unified_diff(
    source.splitlines(True), changed.splitlines(True),
    fromfile='a/sdk/trace/evictedqueue.go', tofile='b/sdk/trace/evictedqueue.go',
)))
for arm in ['before', 'after']:
    replacements = {
        str(local_sdk / 'trace/evictedqueue.go'): str(root / f'evictedqueue-{arm}.go'),
        str(local_sdk / 'trace/evictedqueue_ring_test.go'): str(root / 'evictedqueue_ring_test.go'),
    }
    (root / f'overlay-{arm}.json').write_text(json.dumps({'Replace': replacements}, indent=2) + '\n')
(root / 'source-identity.json').write_text(json.dumps({
    'dependency': 'go.opentelemetry.io/otel/sdk@v1.43.0',
    'source': str(sdk / 'evictedqueue.go'),
    'original_sha256': hashlib.sha256(source.encode()).hexdigest(),
    'candidate_sha256': hashlib.sha256(changed.encode()).hexdigest(),
    'policy': 'Keep Dagger limits and all existing telemetry, cache identities and session ownership unchanged.',
}, indent=2) + '\n')
