// Experimental control checks, excluded from the standalone patch.
package trace

import (
	"os"
	"testing"

	"github.com/stretchr/testify/require"
)

func init() {
	SetEvictedQueueRingDiagnostic(os.Getenv("DAGGER_TEST_RING_QUEUE") == "on")
}

func TestEvictedQueueDiagnosticCapturesMode(t *testing.T) {
	initial := EvictedQueueRingDiagnosticEnabled()
	defer SetEvictedQueueRingDiagnostic(initial)
	SetEvictedQueueRingDiagnostic(false)
	before := newEvictedQueueEvent(3)
	SetEvictedQueueRingDiagnostic(true)
	after := newEvictedQueueEvent(3)
	for i := range 17 {
		before.add(Event{Name: string(rune('a' + i))})
		after.add(Event{Name: string(rune('a' + i))})
		require.Equal(t, before.copy(), after.copy())
		require.Equal(t, before.droppedCount, after.droppedCount)
	}
	SetEvictedQueueRingDiagnostic(false)
	for range 7 {
		before.add(Event{Name: "tail"})
		after.add(Event{Name: "tail"})
		require.Equal(t, before.copy(), after.copy())
	}
}
