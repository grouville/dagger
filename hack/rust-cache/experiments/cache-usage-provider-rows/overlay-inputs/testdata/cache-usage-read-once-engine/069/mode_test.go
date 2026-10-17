package clientdb

import "testing"

func TestSpillBatchBufferDiagnosticModes(t *testing.T) {
	for _, enabled := range []bool{false, true} {
		spillBatchBuffers.Store(enabled)
		TestSpillFileReadSinceOwnsRows(t)
	}
	spillBatchBuffers.Store(false)
}
