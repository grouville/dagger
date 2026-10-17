from pathlib import Path
import json

root = Path(__file__).parent
original = (root / 'evictedqueue-before.go').read_text()
candidate = (root / 'evictedqueue-after.go').read_text()
controlled = candidate.replace('\thead           int\n', '\thead           int\n\tring           bool\n')
controlled = controlled.replace('\t\tcapacity:      capacity,',
    '\t\tcapacity:      capacity,\n\t\tring:          evictedQueueRingDiagnostic.Load(),')
begin = original.index('func (eq *evictedQueue[T]) add(')
end = original.index('\nfunc (eq *evictedQueue[T]) logDropped', begin)
old_add = original[begin:end].replace(']) add(', ']) addOriginal(')
controlled = controlled.replace('func (eq *evictedQueue[T]) add(value T) {', '''func (eq *evictedQueue[T]) add(value T) {
	if !eq.ring {
		eq.addOriginal(value)
		return
	}
	eq.addRing(value)
}

func (eq *evictedQueue[T]) addRing(value T) {''')
controlled += '\n' + old_add + '\n'
(root / 'controlled-evictedqueue.go').write_text(controlled)
(root / 'diagnostic.go').write_text('''// Experimental control only; not part of the standalone patch.
package trace

import "sync/atomic"

var evictedQueueRingDiagnostic atomic.Bool

// The choice is captured by new queues. Existing spans keep their original
// representation when the setting changes between complete commands.
func SetEvictedQueueRingDiagnostic(enabled bool) {
	evictedQueueRingDiagnostic.Store(enabled)
}

func EvictedQueueRingDiagnosticEnabled() bool {
	return evictedQueueRingDiagnostic.Load()
}
''')
debug = (root.parent / 'span-resource-batches/debug.go').read_text()
debug = debug.replace('"runtime/debug"', '"runtime/debug"\n sdktrace "go.opentelemetry.io/otel/sdk/trace"')
target = '\tm.HandleFunc("/debug/span-resource-batches", server.SpanResourceBatchesDiagnostic)'
assert debug.count(target) == 1
debug = debug.replace(target, target + '''
	m.HandleFunc("/debug/otel-evicted-queue", func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost {
			enabled, err := strconv.ParseBool(r.URL.Query().Get("enabled"))
			if err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			sdktrace.SetEvictedQueueRingDiagnostic(enabled)
		} else if r.Method != http.MethodGet {
			http.Error(w, "GET or POST required", http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"enabled": sdktrace.EvictedQueueRingDiagnosticEnabled()})
	})''')
(root / 'debug.go').write_text(debug)
overlay = json.loads((root.parent / 'span-resource-batches/engine-overlay.json').read_text())
overlay['Replace'].update({
    '/tmp/dagger-filesync-snapshot-seeds/cmd/engine/debug.go': str(root / 'debug.go'),
    str(root / 'sdk/trace/evictedqueue.go'): str(root / 'controlled-evictedqueue.go'),
    str(root / 'sdk/trace/diagnostic_evictedqueue.go'): str(root / 'diagnostic.go'),
})
(root / 'engine-overlay.json').write_text(json.dumps(overlay, indent=2) + '\n')
overlay['Replace'][str(root / 'sdk/trace/evictedqueue_ring_test.go')] = str(root / 'evictedqueue_ring_test.go')
overlay['Replace'][str(root / 'sdk/trace/evictedqueue_diagnostic_test.go')] = str(root / 'evictedqueue_diagnostic_test.go')
(root / 'overlay-controlled.json').write_text(json.dumps(overlay, indent=2) + '\n')
