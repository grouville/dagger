// Experimental control only; not part of the standalone patch.
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
